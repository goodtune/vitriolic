import logging
import os.path
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import forms, get_user_model, views
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchVector
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.forms import ModelForm as BaseModelForm
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template import RequestContext
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.http import urlencode
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import patch_cache_control
from guardian.shortcuts import get_objects_for_user
from guardian.utils import get_40x_or_None
from modelforms.forms import ModelForm

from touchtechnology.common.decorators import (
    login_required_m,
    node2extracontext,
    require_POST_m,
)
from touchtechnology.common.default_settings import (
    PAGINATE_BY,
    PROFILE_FORM_CLASS,
)
from touchtechnology.common.utils import (
    get_all_perms_for_model_cached,
    get_perms_for_model,
    model_and_manager,
    select_template_name,
)

logger = logging.getLogger(__name__)


class AlreadyRegistered(Exception):
    pass


class Application(object):
    kwargs_form_class = None
    model_form_bases = (ModelForm,)

    def __init__(self, name, app_name, node=None, **kwargs):
        self.name = name
        self.app_name = app_name
        self.node = node
        # store any instantiation keyword arguments to change behaviour
        self.kwargs = kwargs
        self._spawned = timezone.now()

    def __repr__(self):
        return "<{0}: {1}/{2}/{3}?{4}>".format(
            self.__class__.__name__,
            self.name,
            self.app_name,
            self.node or "",
            urlencode(self.kwargs),
        )

    def _get_namespace(self, cls=None):
        if cls is None:
            cls = self.__class__
        ns, __ = cls.__module__.split(".", 1)
        return ns if ns not in ("apps", self.app_name) else ""

    namespace = property(_get_namespace)

    @property
    def template_base(self):
        # configure the applications base template directory based on
        # namespace and app name
        return os.path.join(self.namespace, self.app_name)

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    @classmethod
    def verbose_name(cls):
        return cls().app_name.title()

    @property
    def version(self):
        """
        Identify version number of the Application. If it is defined as a
        module we look up the import path until we find the module level
        ``get_version`` function, to a maximum depth of 4 levels.
        """
        ver = ""
        for depth in range(1, 5):
            parts = self.__module__.rsplit(".", depth)
            mod = parts[0]
            try:
                ver = import_string("%s.__version__" % mod)
            except ImportError:
                logger.warn('"__version__" not found at "%s"', mod)
            else:
                logger.debug('Identified version "%s" for "%s"', ver, mod)
                break
        name = self.verbose_name
        if callable(name):
            name = name()
        return "{name} {ver}".format(name=_(name), ver=ver)

    @property
    def current_app(self):
        return self.name

    def reverse(self, name, args=None, kwargs=None, prefix=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        named_url = "%s:%s" % (self.app_name, name)
        if prefix:
            named_url = "%s:%s" % (prefix, named_url)
        for key in self.kwargs:
            kwargs.pop(key, None)
        return reverse_lazy(
            named_url, args=args, kwargs=kwargs, current_app=self.current_app
        )

    def redirect(self, *args, **kwargs):
        "Thin wrapper around django.shortcuts.redirect to save on imports"
        return redirect(*args, **kwargs)

    def _template_path(self, filename, *args):
        args = list(reversed([a for a in args if a]))
        for index, arg in enumerate(args, 1):
            yield os.path.join(
                self.template_base, os.path.join(*args[:index]), filename
            )
        yield os.path.join(self.template_base, filename)

    def template_path(self, *args, **kwargs):
        return list(self._template_path(*args, **kwargs))

    def generic_permissions(
        self,
        request,
        model,
        pk=None,
        instance=None,
        post_save_redirect=None,
        templates=None,
        staff_only=None,
        max_checkboxes=None,
        **extra_context
    ):
        # avoid circular import
        from touchtechnology.common.forms.auth import permissionformset_factory

        if instance is None:
            assert pk is not None
            instance = get_object_or_404(model, pk=pk)

        perms = get_perms_for_model(model, add=True)
        has_permission = get_40x_or_None(
            request,
            perms,
            instance,
            return_403=True,
            accept_global_perms=True,
        )

        if has_permission and not request.user.is_superuser:
            return has_permission

        extra_context.update(
            {
                "model": model,
            }
        )

        content_type = ContentType.objects.get_for_model(model)
        queryset = Permission.objects.filter(content_type=content_type).exclude(
            codename__startswith="add_"
        )
        formset_class = permissionformset_factory(
            model, staff_only=staff_only, max_checkboxes=max_checkboxes
        )

        if templates is None:
            templates = self.template_path("permissions.html", model._meta.model_name)

        return self.generic_edit_multiple(
            request,
            model,
            queryset=queryset,
            formset_class=formset_class,
            formset_kwargs={
                "instance": instance,
                "queryset": queryset,
            },
            post_save_redirect=post_save_redirect,
            templates=templates,
            extra_context=extra_context,
        )

    def generic_list(
        self,
        request,
        model_or_manager,
        extra_context=None,
        object_list_name=None,
        paginate_by=None,
        queryset=None,
        templates=None,
        list_templates=None,
        perms=None,
        permission_required=False,
        accept_global_perms=True,
        return_403=None,
        search=None,
        *args,
        **kwargs
    ):

        model, manager = model_and_manager(model_or_manager)

        # If not explicitly declared, redirect the user to login if they are
        # currently anonymous. If they are already identified, we can safely
        # return an HTTP 403 Forbidden.
        if return_403 is None:
            return_403 = not request.user.is_anonymous

        if queryset is None:
            queryset = manager.all()

        # Search should be an iterable of fields to look into.
        if search is not None:
            terms = request.GET.get("search")
            if terms is not None:
                queryset = queryset.annotate(
                    search=SearchVector(*search),
                ).filter(search=terms)

        # Implement permission checking for list of objects, will filter the
        # list to those objects the user is entitled to work on if we do not
        # throw an HTTP 403 for no permission.
        if permission_required:
            if perms is None:
                perms = get_all_perms_for_model_cached(model)

            # Determine the user's permission to see the list using the
            # get_40x_or_None - saves decorating view method with
            # @permission_required_or_403
            has_permission = get_40x_or_None(
                request,
                perms,
                return_403=return_403,
                accept_global_perms=accept_global_perms,
                any_perm=True,
            )

            global_perms = any([request.user.has_perm(p) for p in perms])

            # If the user does not have any global permissions then adjust the
            # queryset to return only the objects they can act on.
            if not global_perms:
                queryset = get_objects_for_user(
                    request.user, perms, queryset, use_groups=True, any_perm=True
                )

            # If permission is denied, return the response. May already have
            # thrown an exception by now.
            if not queryset and has_permission is not None:
                return has_permission

        if extra_context is None:
            extra_context = {}

        if object_list_name is None:
            object_list_name = "{0}_list".format(model._meta.model_name)

        if templates is None:
            templates = self.template_path("list.html", model._meta.model_name)

        if list_templates is None:
            list_templates = self.template_path("list.inc.html", model._meta.model_name)
            # Always tack the mvp theme version on the end as a fallback.
            list_templates.append("mvp/list.inc.html")

        # Determine the namespace of this Application, so we can construct
        # view names to pass to the template engine to reverse CRUD URI's.
        create_url_name = "%s:add" % request.resolver_match.namespace
        create_url_kwargs = request.resolver_match.kwargs.copy()
        create_url_kwargs.pop("admin", None)
        create_url_kwargs.pop("component", None)

        # We can't leave this until the template is rendered because it throws
        # exceptions (stupid!) so we'll avoid lazy evaluation and pass None if
        # the create view doesn't exist for this model.
        try:
            create_url = reverse(
                create_url_name,
                args=request.resolver_match.args,
                kwargs=create_url_kwargs,
            )
        except NoReverseMatch:
            create_url = None

        context = {
            "queryset": queryset,
            object_list_name: queryset,
            "object_list": queryset,
            "is_paginated": False,
            "page": None,
            "page_num": None,
            "paginator": None,
            "model": manager.none(),
            "template": select_template_name(templates),
            "list_template": select_template_name(list_templates),
            # Is search enabled?
            "searchable": bool(search),
            "search": request.GET.get("search", ""),
            # Pass to template the name permissions, so we can re-use template
            # code to generically list and add/change/delete objects
            "add_perm": "%s.add_%s" % (model._meta.app_label, model._meta.model_name),
            "view_perm": "%s.view_%s" % (model._meta.app_label, model._meta.model_name),
            "change_perm": "%s.change_%s"
            % (model._meta.app_label, model._meta.model_name),
            "delete_perm": "%s.delete_%s"
            % (model._meta.app_label, model._meta.model_name),
            "create_url": create_url,
        }

        if paginate_by is None:
            paginate_by = PAGINATE_BY

        # Ensure that paginate_by is an integer to prevent ZeroDivisionError
        # inside the Django paginator steps.
        paginate_by = int(paginate_by)

        if paginate_by > 0:
            try:
                page_num = int(request.GET.get("page", 1))
            except TypeError:
                page_num = 1

            paginator = Paginator(queryset, paginate_by)

            try:
                page = paginator.page(page_num)
            except EmptyPage:
                page = paginator.page(paginator.num_pages)

            context.update(
                {
                    object_list_name: page.object_list,
                    "object_list": page.object_list,
                    "is_paginated": paginator.num_pages > 1,
                    "page": page,
                    "page_num": page_num,
                    "paginator": paginator,
                }
            )

        context.update(extra_context)
        return self.render(request, templates, context, *args, **kwargs)

    def generic_detail(
        self, request, model_or_manager, templates=None, extra_context=None, **kwargs
    ):
        model, manager = model_and_manager(model_or_manager)
        instance = get_object_or_404(manager, **kwargs)

        context = {
            "object": instance,
            model._meta.model_name: instance,
            "model": manager.none(),
        }
        context.update(extra_context or {})

        if templates is None:
            templates = self.template_path("detail.html", model._meta.model_name)

        return self.render(request, templates, context)

    def generic_edit(
        self,
        request,
        model_or_manager,
        pk=None,
        instance=None,
        form_class=None,
        form_kwargs=None,
        form_fields="__all__",
        form_widgets=None,
        pre_save_callback=lambda o: o,
        post_save_callback=lambda o: None,
        post_save_redirect=None,
        templates=None,
        changed_messages=((messages.SUCCESS, _("Your {model} has been " "saved.")),),
        unchanged_messages=((messages.INFO, _("Your {model} was not changed.")),),
        permission_required=False,
        perms=None,
        accept_global_perms=True,
        return_403=None,
        related=None,
        extra_context=None,
        always_save=False,
    ):

        model, manager = model_and_manager(model_or_manager)

        # If not explicitly declared, redirect the user to login if they are
        # currently anonymous. If they are already identified, we can safely
        # return an HTTP 403 Forbidden.
        if return_403 is None:
            return_403 = not request.user.is_anonymous

        if instance is None and pk is not None:
            instance = get_object_or_404(manager, pk=pk)

        if form_kwargs is None:
            form_kwargs = {}

        if extra_context is None:
            extra_context = {}

        if post_save_redirect is None:
            redirect_to = urljoin(request.path, "..") if pk is None else request.path
            post_save_redirect = self.redirect(redirect_to)

        # Implement permission checking for specified object instance, throw
        # an HTTP 403 (using django-guardian configuration) when the user is
        # not entitled to edit the instance.
        if permission_required:

            # If no perms are specified, build sensible default using built in
            # permission types that come batteries included with Django.
            if perms is None:
                perms = get_perms_for_model(model, change=True)

                # When there is no pk value, we're doing a creation and should
                # have permission to create the object.
                if pk is None or instance.pk is None:
                    perms = get_perms_for_model(model, add=True)

            # Determine the user's permission to edit this object using the
            # get_40x_or_None - saves decorating view method with
            # @permission_required_or_403
            has_permission = get_40x_or_None(
                request,
                perms,
                obj=instance,
                return_403=return_403,
                accept_global_perms=accept_global_perms,
            )

            # If permission is denied, return the response. May already have
            # thrown an exception by now.
            if has_permission is not None:
                return has_permission

        # If the developer has not provided a custom form, then dynamically
        # construct a default ModelForm for them.
        if form_class is None:
            meta_class = type(
                smart_str("Meta"),
                (),
                {"model": model, "fields": form_fields, "widgets": form_widgets},
            )
            form_class = type(
                smart_str("EditForm"), self.model_form_bases, {"Meta": meta_class}
            )

        # Whether we've dynamically constructed our form_class or not, check to
        # ensure that we've inherited from all the bases. Log when we haven't,
        # but don't raise any exceptions.
        for base in self.model_form_bases:
            if not issubclass(form_class, base):
                logger.error('"%s" does not inherit "%s"', form_class, base)

        # Pass the instance to the form constructor if this is a ModelForm
        # subclass, otherwise it will need to be explicitly added to
        # form_kwargs if expected.
        if issubclass(form_class, BaseModelForm) and instance is not None:
            form_kwargs.setdefault("instance", instance)

        # Vanilla form processing here, take the post data and files, create
        # an instance of form_class, save and redirect.
        if request.method == "POST":
            form = form_class(data=request.POST, files=request.FILES, **form_kwargs)
            if form.is_valid():
                replace = dict(
                    model=smart_str(model._meta.verbose_name),
                    models=smart_str(model._meta.verbose_name_plural),
                )
                if always_save or form.has_changed():
                    res = pre_save_callback(form.instance)
                    if isinstance(res, HttpResponse):
                        return res
                    obj = form.save()
                    callback_res = post_save_callback(obj)
                    for level, message in changed_messages:
                        messages.add_message(request, level, message.format(**replace))
                    if callback_res is not None:
                        return callback_res
                else:
                    for level, message in unchanged_messages:
                        messages.add_message(request, level, message.format(**replace))
                return post_save_redirect
        else:
            form = form_class(**form_kwargs)

        if templates is None:
            templates = self.template_path("edit.html", model._meta.model_name)
            templates.append("edit.html")

        context = {
            "model": manager.none(),
            "template": select_template_name(templates),
            "form": form,
            "object": instance,
            "related": related,
            "cancel_url": post_save_redirect.url,
        }
        context.update(extra_context or {})

        return self.render(request, templates, context)

    def generic_edit_multiple(
        self,
        request,
        model_or_manager,
        extra_context=None,
        formset_class=None,
        formset_kwargs=None,
        formset_fields="__all__",
        post_save_callback=lambda o: None,
        post_save_redirect_args=None,
        post_save_redirect_kwargs=None,
        post_save_redirect=None,
        templates=None,
        changed_messages=None,
        perms=None,
        permission_required=False,
        accept_global_perms=True,
        return_403=None,
        *args,
        **kwargs
    ):

        if extra_context is None:
            extra_context = {}

        if formset_kwargs is None:
            formset_kwargs = {}

        if post_save_redirect_args is None:
            post_save_redirect_args = ()

        if post_save_redirect_kwargs is None:
            post_save_redirect_kwargs = {}

        if changed_messages is None:
            changed_messages = (
                (messages.SUCCESS, _("Your {models} have been saved.")),
            )

        # If not explicitly declared, redirect the user to login if they are
        # currently anonymous. If they are already identified, we can safely
        # return an HTTP 403 Forbidden.
        if return_403 is None:
            return_403 = not request.user.is_anonymous

        # Try and introspect the model if possible.
        model, manager = model_and_manager(model_or_manager)
        queryset = manager.all()

        # Implement permission checking for list of objects, will filter the
        # list to those objects the user is entitled to work on if we do not
        # throw an HTTP 403 for no permission.
        if permission_required:
            if perms is None:
                perms = get_all_perms_for_model_cached(model)

            # Determine the user's permission to see the list using the
            # get_40x_or_None - saves decorating view method with
            # @permission_required_or_403
            has_permission = get_40x_or_None(
                request,
                perms,
                return_403=return_403,
                accept_global_perms=accept_global_perms,
                any_perm=True,
            )

            # If the user does not have any global permissions then adjust the
            # queryset to return only the objects they can act on.
            if not any([request.user.has_perm(p) for p in perms]):
                queryset = get_objects_for_user(
                    request.user, perms, queryset, use_groups=True, any_perm=True
                )

            # If permission is denied, return the response. May already have
            # thrown an exception by now.
            if not queryset and has_permission is not None:
                return has_permission

            queryset = get_objects_for_user(
                request.user, perms, queryset, any_perm=True
            )

        # If queryset is not already specified as a keyword argument to the
        # formset attach it now. Value in formset_kwargs will take precedence.
        queryset = formset_kwargs.pop("queryset", queryset)

        # If the developer has not provided a custom formset, then dynamically
        # construct a default ModelFormSet for them.
        if formset_class is None:
            formset_class = modelformset_factory(model, extra=0, fields=formset_fields)

        if post_save_redirect is None:
            redirect_to = urljoin(request.path, "..")
            post_save_redirect = self.redirect(redirect_to)

        # Vanilla formset processing here, take the post data and files, create
        # an instance of formset_class, save and redirect.
        if request.method == "POST":
            formset = formset_class(
                data=request.POST,
                files=request.FILES,
                queryset=queryset,
                **formset_kwargs
            )
            if formset.is_valid():
                replace = dict(
                    model=smart_str(model._meta.verbose_name),
                    models=smart_str(model._meta.verbose_name_plural),
                )
                objects = formset.save()
                for each in objects:
                    post_save_callback(each)
                for level, message in changed_messages:
                    messages.add_message(request, level, message.format(**replace))
                if isinstance(post_save_redirect, HttpResponse):
                    return post_save_redirect
                redirect_to = self.reverse(
                    post_save_redirect,
                    args=post_save_redirect_args,
                    kwargs=post_save_redirect_kwargs,
                )
                return redirect(redirect_to)
        else:
            formset = formset_class(queryset=queryset, **formset_kwargs)

        context = {
            "model": manager.none(),
            "formset": formset,
            "object_list": queryset,
        }
        context.update(extra_context)

        if templates is None:
            templates = self.template_path("edit_multiple.html", model._meta.model_name)
            templates.append("edit_multiple.html")

        return self.render(request, templates, context)

    def generic_edit_related(
        self,
        request,
        model_or_manager,
        related_model,
        extra_context={},
        form_class=None,
        form_kwargs={},
        form_fields="__all__",
        form_widgets=None,
        formset_class=None,
        formset_kwargs={},
        formset_fields="__all__",
        instance=None,
        pk=None,
        post_save_callback=lambda o: None,
        post_save_redirect_args=(),
        post_save_redirect_kwargs={},
        post_save_redirect="index",
        post_save_related_callback=lambda o: None,
        templates=None,
    ):

        model, manager = model_and_manager(model_or_manager)

        if instance is None and pk is not None:
            instance = get_object_or_404(manager, pk=pk)

        # If the developer has not provided a custom form, then dynamically
        # construct a default ModelForm for them.
        if form_class is None:
            meta_class = type(
                smart_str("Meta"),
                (),
                {"model": model, "fields": form_fields, "widgets": form_widgets},
            )
            form_class = type(
                smart_str("EditForm"), self.model_form_bases, {"Meta": meta_class}
            )

        # If the developer has not provided a custom formset, then dynamically
        # construct a default one with inlineformset_factory.
        if formset_class is None:
            formset_class = inlineformset_factory(
                model, related_model, fields=formset_fields, extra=0
            )

        # Add form and formset prefixes if not already present in the kwargs
        form_kwargs.setdefault("prefix", "form")
        formset_kwargs.setdefault("prefix", "formset")

        # Keep verbose names for model and related_model for use in messages
        model_verbose_name = model._meta.verbose_name.lower()
        related_verbose_name_plural = related_model._meta.verbose_name_plural.lower()
        verbose = {
            "model_verbose_name": model_verbose_name,
            "related_verbose_name_plural": related_verbose_name_plural,
        }

        # Vanilla form processing here, take the post data and files, create
        # an instance of form_class, save and redirect.
        if request.method == "POST":
            sid = transaction.savepoint()

            form = form_class(
                data=request.POST, files=request.FILES, instance=instance, **form_kwargs
            )

            if form.is_valid():
                obj = form.save()
                logger.debug("Saved %r to database.", obj)

                # Rebuild formset with updated instance object.
                formset = formset_class(
                    data=request.POST,
                    files=request.FILES,
                    instance=obj,
                    **formset_kwargs
                )

                if formset.is_valid():
                    logger.debug(
                        "Related formset is valid, if we don't "
                        "complete successfully then an exception "
                        "will bubble up."
                    )
                    related = formset.save()
                    post_save_callback(obj)
                    for each in related:
                        post_save_related_callback(each)
                    transaction.savepoint_commit(sid)
                    messages.add_message(
                        request,
                        messages.SUCCESS,
                        _(
                            "Your %(model_verbose_name)s and "
                            "%(related_verbose_name_plural)s "
                            "have been saved."
                        )
                        % verbose,
                    )
                    if isinstance(post_save_redirect, HttpResponse):
                        return post_save_redirect
                    redirect_to = self.reverse(
                        post_save_redirect,
                        args=post_save_redirect_args,
                        kwargs=post_save_redirect_kwargs,
                    )
                    return redirect(redirect_to)

                # if we've made it out without returning a HttpRedirect then
                # we should not be persisting the result.
                logger.debug("ROLLBACK, we were not redirected.")
                transaction.savepoint_rollback(sid)

            else:
                formset = formset_class(
                    data=request.POST,
                    files=request.FILES,
                    instance=instance,
                    **formset_kwargs
                )

        else:
            form = form_class(instance=instance, **form_kwargs)
            formset = formset_class(instance=instance, **formset_kwargs)

        context = {
            "model": manager.none(),
            "form": form,
            "formset": formset,
            "object": instance,
            "media": form.media + formset.media,
            # For template compatibility, we don't use related ourselves but this
            # method is only used in touchtechnology.content.admin
            "related": (),
        }
        context.update(extra_context)

        if templates is None:
            templates = self.template_path("edit.related.html", model._meta.model_name)

        return self.render(request, templates, context)

    @require_POST_m
    def generic_delete(
        self,
        request,
        model_or_manager,
        pk,
        post_delete_redirect=None,
        perms=None,
        permission_required=False,
        accept_global_perms=True,
        return_403=None,
        **kwargs
    ):

        model, manager = model_and_manager(model_or_manager)

        instance = get_object_or_404(manager, pk=pk)

        # If not explicitly declared, redirect the user to login if they are
        # currently anonymous. If they are already identified, we can safely
        # return an HTTP 403 Forbidden.
        if return_403 is None:
            return_403 = not request.user.is_anonymous

        # Implement permission checking for specified object instance, throw
        # an HTTP 403 (using django-guardian configuration) when the user is
        # not entitled to edit the instance.
        if permission_required:

            # If no perms are specified, build sensible default using built in
            # permission types that come batteries included with Django.
            if perms is None:
                perms = get_perms_for_model(model, delete=True)

            # Determine the user's permission to edit this object using the
            # get_40x_or_None - saves decorating view method with
            # @permission_required_or_403
            has_permission = get_40x_or_None(
                request,
                perms,
                obj=instance,
                return_403=return_403,
                accept_global_perms=accept_global_perms,
            )

            # If permission is denied, return the response. May already have
            # thrown an exception by now.
            if has_permission is not None:
                return has_permission

        if post_delete_redirect is None:
            redirect_to = urljoin(request.path, "../..")
            post_delete_redirect = self.redirect(redirect_to)

        instance.delete()
        messages.add_message(
            request,
            messages.SUCCESS,
            _("The %s has been deleted.") % model._meta.verbose_name,
        )
        return post_delete_redirect

    def context_instance(self, request, **kwargs):
        return RequestContext(request, current_app=self.current_app, **kwargs)

    def render_to_string(self, request, templates, context, **kwargs):
        context_instance = self.context_instance(request)
        return render_to_string(templates, context, context_instance, **kwargs)

    def render(self, request, templates, context, tz=None, **kwargs):
        logger.debug(
            "{app}.render: {request.path}".format(
                app=self.__class__.__name__, request=request
            )
        )
        context.update({"application": self})
        kwargs.setdefault("context", context)

        response = TemplateResponse(request, templates, **kwargs)
        response.current_app = self.current_app

        if tz is not None:
            with timezone.override(tz):
                response.render()

        if not request.user.is_anonymous:
            patch_cache_control(response, private=True)
        return response


class AccountsSite(Application):
    def __init__(self, name="accounts", app_name="accounts", *args, **kwargs):
        super(AccountsSite, self).__init__(name=name, app_name=app_name)
        self.profile_form_class = kwargs.pop("profile_form_class", PROFILE_FORM_CLASS)
        self.user_model = get_user_model()

    @property
    def set_password_form(self):
        class SetPasswordForm(forms.SetPasswordForm):
            def __init__(slf, user, *a, **kw):
                super(SetPasswordForm, slf).__init__(user, *a, **kw)
                if user:
                    slf.user = self.user_model.objects.get(pk=user.pk)

        return SetPasswordForm

    @property
    def password_change_form(self):
        class PasswordChangeForm(forms.PasswordChangeForm):
            def __init__(slf, user, *a, **kw):
                super(PasswordChangeForm, slf).__init__(user, *a, **kw)
                if user:
                    slf.user = self.user_model.objects.get(pk=user.pk)

        return PasswordChangeForm

    @property
    def template_base(self):
        return "registration"

    def get_urls(self):
        urlpatterns = [
            path("login/", self.login, name="login"),
            path("logout/", self.logout, name="logout"),
            path("password-change/", self.password_change, name="password_change"),
            path(
                "password-change/done/",
                self.password_change_done,
                name="password_change_done",
            ),
            path("password-reset/", self.password_reset, name="password_reset"),
            path(
                "password-reset/done/",
                self.password_reset_done,
                name="password_reset_done",
            ),
            path(
                "reset/<uidb64>/<token>/",
                self.password_reset_confirm,
                name="password_reset_confirm",
            ),
            path(
                "reset/done/",
                self.password_reset_complete,
                name="password_reset_complete",
            ),
            path("profile/", self.profile, name="profile"),
            path(r"", self.index, name="index"),
        ]
        return urlpatterns

    @node2extracontext
    def login(self, request, extra_context, *args, **kwargs):
        form_class = getattr(
            settings,
            "AUTHENTICATION_FORM_CLASS",
            "django.contrib.auth.forms.AuthenticationForm",
        )
        authentication_form = import_string(form_class)
        view = views.LoginView.as_view(
            authentication_form=authentication_form, extra_context=extra_context
        )
        return view(request, *args, **kwargs)

    @node2extracontext
    def logout(self, request, extra_context, *args, **kwargs):
        view = views.LogoutView.as_view(extra_context=extra_context)
        return view(request, *args, **kwargs)

    @node2extracontext
    def password_change(self, request, extra_context, *args, **kwargs):
        success_url = kwargs.pop(
            "post_change_redirect", self.reverse("password_change_done")
        )
        form_class = kwargs.pop("password_change_form", self.password_change_form)
        view = views.PasswordChangeView.as_view(
            form_class=form_class, success_url=success_url, extra_context=extra_context
        )
        return view(request, *args, **kwargs)

    @node2extracontext
    def password_change_done(self, request, extra_context, *args, **kwargs):
        view = views.PasswordChangeDoneView.as_view(extra_context=extra_context)
        return view(request, *args, **kwargs)

    @node2extracontext
    def password_reset(self, request, extra_context, *args, **kwargs):
        success_url = kwargs.pop(
            "post_reset_redirect", self.reverse("password_reset_done")
        )
        view = views.PasswordResetView.as_view(
            success_url=success_url, extra_context=extra_context
        )
        return view(request, *args, **kwargs)

    @node2extracontext
    def password_reset_done(self, request, extra_context, *args, **kwargs):
        view = views.PasswordResetDoneView.as_view(extra_context=extra_context)
        return view(request, *args, **kwargs)

    @node2extracontext
    def password_reset_confirm(self, request, extra_context, *args, **kwargs):
        success_url = kwargs.pop(
            "post_reset_redirect", self.reverse("password_reset_complete")
        )
        form_class = kwargs.pop("set_password_form", self.set_password_form)
        view = views.PasswordResetConfirmView.as_view(
            form_class=form_class,
            success_url=success_url,
            extra_context=extra_context,
        )
        return view(request, *args, **kwargs)

    @node2extracontext
    def password_reset_complete(self, request, extra_context, *args, **kwargs):
        view = views.PasswordResetCompleteView.as_view(extra_context=extra_context)
        return view(request, *args, **kwargs)

    def activation_complete(self, request, *args, **kwargs):
        context = {}
        context.update(kwargs)
        templates = self.template_path("activation_complete.html")
        return self.render(request, templates, context)

    def index(self, request, *args, **kwargs):
        return redirect(settings.LOGIN_REDIRECT_URL)

    @login_required_m
    def profile(self, request, *args, **kwargs):
        form_class = import_string(self.profile_form_class)

        if request.method == "POST":
            form = form_class(data=request.POST, instance=request.user)
            if form.is_valid():
                if form.has_changed():
                    form.save()
                    messages.add_message(
                        request, messages.SUCCESS, _("Your changes have been saved.")
                    )
                else:
                    messages.add_message(
                        request, messages.INFO, _("You did not make any changes.")
                    )
                return redirect(".")
        else:
            form = form_class(instance=request.user)

        context = {
            "form": form,
        }
        context.update(kwargs)

        templates = self.template_path("profile.html")
        return self.render(request, templates, context)
