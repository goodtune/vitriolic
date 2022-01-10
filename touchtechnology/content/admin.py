from __future__ import unicode_literals

import logging
import os

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import include, path, re_path, resolve, reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from first import first

from touchtechnology.admin.base import AdminComponent
from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.common.decorators import (
    require_POST_m,
    staff_login_required_m,
)
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.forms import (
    FileUploadForm,
    NewFolderForm,
    NewPlaceholderSitemapNodeForm,
    NewSitemapNodeForm,
    Page,
    PageContentFormset,
    PageForm,
    PlaceholderConfigurationBase,
    PlaceholderContentFormset,
    PlaceholderSitemapNodeForm,
    RedirectEditForm,
    SitemapNodeForm,
)
from touchtechnology.content.models import (
    Chunk,
    PageContent,
    Placeholder,
    Redirect,
)

logger = logging.getLogger(__name__)


class ContentAdminComponent(AdminComponent):
    verbose_name = _("Content")

    filter = Q(content_type__app_label="content") | Q(content_type__isnull=True)

    def __init__(self, app, name="content", app_name="content"):
        super(ContentAdminComponent, self).__init__(app, name, app_name)

    def get_urls(self):
        folder_patterns = (
            [
                path("add/", self.edit_folder, name="add"),
                path("<int:pk>/", self.edit_folder, name="edit"),
                path("<int:pk>/delete/", self.delete_folder, name="delete"),
            ],
            self.app_name,
        )

        page_patterns = (
            [
                path("add/", self.edit_page, name="add"),
                path("<int:pk>/", self.edit_page, name="edit"),
                path("<int:pk>/delete/", self.delete_page, name="delete"),
                path("<int:pk>/permission/", self.perms_sitemapnode, name="perms"),
            ],
            self.app_name,
        )

        redirect_patterns = (
            [
                path("", self.list_redirects, name="list"),
                path("create/", self.edit_redirect, name="add"),
                path("<int:pk>/", self.edit_redirect, name="edit"),
                path("<int:pk>/delete/", self.delete_redirect, name="delete"),
                path("<int:pk>/permission/", self.perms_redirect, name="perms"),
            ],
            self.app_name,
        )

        placeholder_patterns = (
            [
                path("", self.list_placeholders, name="list"),
                path("create/", self.edit_placeholder_x, name="add"),
                path("<int:pk>/", self.edit_placeholder_x, name="edit"),
                path("<int:pk>/delete/", self.delete_placeholder_x, name="delete"),
                # path("<int:pk>/permission/", self.perms_placeholder, name="delete"),
            ],
            self.app_name,
        )

        application_patterns = (
            [
                path("add/", self.edit_application_node, name="add"),
                path("<int:pk>/", self.edit_application_node, name="edit"),
                path("<int:pk>/delete/", self.delete_application_node, name="delete"),
                path("<int:pk>/permission/", self.perms_sitemapnode, name="perms"),
            ],
            self.app_name,
        )

        chunk_patterns = (
            [
                path("", self.list_chunks, name="list"),
                path("create/", self.edit_chunk, name="add"),
                path("<int:pk>/", self.edit_chunk, name="edit"),
                path("<int:pk>/delete/", self.delete_chunk, name="delete"),
                path("<int:pk>/permission/", self.perms_chunk, name="perms"),
            ],
            self.app_name,
        )

        files_patterns = (
            [
                re_path(
                    r"^(?P<path>.+/)?(?P<filename>[^/]+?)/rm/$", self.rm, name="delete"
                ),
                re_path(r"^(?P<path>.+/)rmdir/$", self.rm, name="delete"),
                path("", self.ls, name="list"),
                re_path(r"^(?P<path>.+)$", self.ls, name="edit"),
            ],
            self.app_name,
        )

        urlpatterns = [
            path("", self.list_pages, name="index"),
            path("folder/", include(folder_patterns, namespace="folder")),
            path("page/", include(page_patterns, namespace="page")),
            path("redirect/", include(redirect_patterns, namespace="redirect")),
            path(
                "placeholder/",
                include(placeholder_patterns, namespace="real_placeholder"),
            ),
            path(
                "application/", include(application_patterns, namespace="placeholder")
            ),
            path("chunk/", include(chunk_patterns, namespace="chunk")),
            path("files/", include(files_patterns, namespace="media")),
        ]
        return urlpatterns

    def dropdowns(self):
        dl = (
            (_("Sitemap"), self.reverse("index"), "sitemap"),
            (_("Media"), self.reverse("media:list"), "folder-open"),
            (_("Chunks"), self.reverse("chunk:list"), "pencil-square-o"),
            (_("Redirects"), self.reverse("redirect:list"), "reply"),
            (_("Applications"), self.reverse("real_placeholder:list"), "puzzle-piece"),
        )
        return dl

    # Generic views - trial before moving onto Application

    def generic_parent_edit_related(
        self,
        request,
        pk,
        parent_model,
        child_model,
        child_related_model,
        parent_form_class=None,
        child_form_class=None,
        child_formset_class=None,
        post_save_redirect=None,
        *args,
        **kwargs
    ):
        if pk is not None:
            instance = get_object_or_404(parent_model, pk=pk)
        else:
            instance = None
        if post_save_redirect is None:
            post_save_redirect = self.redirect(self.reverse("index"))
        return self.generic_edit_related(
            request,
            child_model,
            child_related_model,
            instance=instance,
            form_class=child_form_class,
            form_kwargs={
                "parent_form_class": parent_form_class,
                "parent_form_kwargs": {"user": request.user},
            },
            formset_class=child_formset_class,
            post_save_redirect=post_save_redirect,
            extra_context=kwargs,
        )

    # Shared perms view

    def perms_sitemapnode(self, request, pk, **extra_context):
        return self.generic_permissions(request, SitemapNode, pk=pk, **extra_context)

    # Folder views -- folders are just SitemapNode's with no links

    @staff_login_required_m
    def edit_folder(self, request, pk=None, *args, **kwargs):
        form_class = NewSitemapNodeForm if pk is None else SitemapNodeForm
        return self.generic_edit(
            request,
            SitemapNode,
            pk=pk,
            form_class=form_class,
            related=(),
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_folder(self, request, pk, *args, **kwargs):
        node = get_object_or_404(SitemapNode, pk=pk)
        if not node.is_leaf_node():
            raise Http404
        return self.generic_delete(request, SitemapNode, pk=pk, extra_context=kwargs)

    # Page views

    @staff_login_required_m
    def list_pages(self, request, **extra_context):
        try:
            root = SitemapNode.objects.get(pk=request.GET["r"])
            descendants = root.get_descendants()
            nodes = descendants.filter(self.filter).filter(level=root.level + 1)
        except KeyError:
            nodes = SitemapNode.objects.filter(self.filter).filter(level=0)
        return self.generic_list(
            request,
            nodes,
            paginate_by=0,
            permission_required=True,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def edit_page(self, request, pk=None, **extra_context):
        post_save_redirect = None
        if pk is not None:
            instance = get_object_or_404(SitemapNode, pk=pk)
            if instance.parent_id:
                post_save_redirect = self.redirect(
                    self.reverse("index") + "?r=%d" % instance.parent_id
                )
        return self.generic_parent_edit_related(
            request,
            pk,
            parent_model=SitemapNode,
            child_model=Page,
            child_related_model=PageContent,
            parent_form_class=SitemapNodeForm,
            child_form_class=PageForm,
            child_formset_class=PageContentFormset,
            post_save_redirect=post_save_redirect,
            **extra_context
        )

    @staff_login_required_m
    def delete_page(self, request, pk, *args, **kwargs):
        node = get_object_or_404(SitemapNode, pk=pk)

        if request.method == "POST":
            # verify that we are only operating on a leaf node
            if not node.is_leaf_node():
                raise Http404
            # if this was not a POST request, we don't make changes to the
            # database, we just display the warning page.
            page = node.object
            page.content.all().delete()
            page.delete()
            node.delete()
            redirect_to = self.reverse("index")
            if node.parent:
                redirect_to += "?r=%d" % node.parent_id
            return HttpResponseRedirect(redirect_to)

        context = {
            "object": node,
        }
        context.update(kwargs)

        templates = self.template_path("delete_confirm.html")
        return self.render(request, templates, context)

    # Redirect views

    @staff_login_required_m
    def list_redirects(self, request, *args, **kwargs):
        return self.generic_list(
            request, Redirect, permission_required=True, extra_context=kwargs
        )

    @staff_login_required_m
    def edit_redirect(self, request, pk=None, *args, **kwargs):
        return self.generic_edit(
            request,
            Redirect,
            pk=pk,
            form_class=RedirectEditForm,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_redirect(self, request, pk, *args, **kwargs):
        return self.generic_delete(
            request, Redirect, pk=pk, permission_required=True, extra_context=kwargs
        )

    @staff_login_required_m
    def perms_redirect(self, request, pk, *args, **kwargs):
        return self.generic_permissions(request, Redirect, pk=pk, **kwargs)

    # Application views

    @staff_login_required_m
    def list_placeholders(self, request, *args, **kwargs):
        return self.generic_list(
            request,
            Placeholder,
            paginate_by=0,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_placeholder_x(self, request, pk=None, *args, **kwargs):
        return self.generic_edit(
            request, Placeholder, pk=pk, permission_required=True, extra_context=kwargs
        )

    @staff_login_required_m
    def delete_placeholder_x(self, request, pk, *args, **kwargs):
        return self.generic_delete(
            request, Placeholder, pk=pk, permission_required=True, extra_context=kwargs
        )

    @staff_login_required_m
    def edit_application_node(self, request, pk=None, **extra_context):
        kwargs_form_class = PlaceholderConfigurationBase

        if pk is None:
            instance = SitemapNode()
            form_class = NewPlaceholderSitemapNodeForm
        else:
            instance = get_object_or_404(SitemapNode, pk=pk)
            form_class = PlaceholderSitemapNodeForm
            try:
                site = instance.object.site(instance)
            except ValueError:
                logger.exception("Application is unavailable, " "no custom form class.")
            else:
                kwargs_form_class = site.kwargs_form_class or kwargs_form_class

        if request.method == "POST":
            form = form_class(data=request.POST, instance=instance, user=request.user)
            kw = kwargs_form_class(
                data=request.POST, instance=instance, prefix="kw", user=request.user
            )
            copy = PlaceholderContentFormset(
                data=request.POST, instance=instance, prefix="copy"
            )
            if form.is_valid() and kw.is_valid() and copy.is_valid():
                form.save()
                kw.save()
                copy.save()

                redirect_to = self.reverse("index")
                if instance.parent:
                    redirect_to += "?r=%d" % instance.parent_id

                # post_save_callback if we ever move this to a generic_edit
                # pattern in future.
                instance.object.invalidate_cache()

                return HttpResponseRedirect(redirect_to)
        else:
            form = form_class(instance=instance, user=request.user)
            kw = kwargs_form_class(instance=instance, prefix="kw", user=request.user)
            copy = PlaceholderContentFormset(instance=instance, prefix="copy")

        context = {
            "form": form,
            "formsets": {
                "kwargs": kw,
                "copy": copy,
            },
            "formset_media": kw.media + copy.media,
            "node": instance,
            "model": Placeholder.objects.none(),
        }
        context.update(extra_context)

        templates = self.template_path("edit_application.html")
        return self.render(request, templates, context)

    @require_POST_m
    @staff_login_required_m
    def delete_application_node(self, request, pk, *args, **kwargs):
        node = get_object_or_404(SitemapNode, pk=pk)

        if request.method == "POST":
            # verify that we are only operating on a leaf node
            if not node.is_leaf_node():
                raise Http404
            redirect_to = reverse("admin:content:index", current_app=self.app)
            if node.parent:
                redirect_to += "?r=%d" % node.parent_id
            # if this was not a POST request, we don't make changes to the
            # database, we just display the warning page.
            node.delete()

            return HttpResponseRedirect(redirect_to)

        context = {
            "object": node,
        }
        context.update(kwargs)

        templates = self.template_path("delete_confirm.html")
        return self.render(request, templates, context)

    # Chunk views

    @staff_login_required_m
    def list_chunks(self, request, *args, **kwargs):
        return self.generic_list(request, Chunk, extra_context=kwargs)

    @staff_login_required_m
    def edit_chunk(self, request, pk=None, *args, **kwargs):
        return self.generic_edit(request, Chunk, pk=pk, extra_context=kwargs)

    @staff_login_required_m
    def delete_chunk(self, request, pk, **extra_context):
        return self.generic_delete(request, Chunk, pk=pk, extra_context=extra_context)

    @staff_login_required_m
    def perms_chunk(self, request, pk, *args, **kwargs):
        return self.generic_permissions(request, Chunk, pk=pk, **kwargs)

    @staff_login_required_m
    def ls(self, request, path=None, *args, **kwargs):
        try:
            directories, files = default_storage.listdir(path or ".")
        except OSError as e:
            raise Http404(e)

        directories.sort()
        files.sort()

        parentdir = os.path.dirname(path[:-1]) or "ROOT" if path else ""

        writable = True  # presume it is, and fail gracefully if it isn't
        if path and hasattr(default_storage, "writable"):
            writable = default_storage.writable(path)

        # Both types for Form expect a path to be passed in, set up the base.
        form_kwargs = dict(path=path)

        if request.method == "POST":
            # Give the Forms the POST and FILES from the request
            form_kwargs.update(dict(data=request.POST, files=request.FILES))

            folder_form = NewFolderForm(prefix="folder", **form_kwargs)
            file_form = FileUploadForm(prefix="file", **form_kwargs)

            if folder_form.is_valid() and file_form.is_valid():
                redirect_to = "."
                saved = None

                if folder_form.has_changed():
                    saved = folder_form.save()
                    logger.debug("created folder %s", saved)
                    folder_name = os.path.basename(saved)
                    messages.success(
                        request, _('Opened new folder "%s".') % folder_name
                    )
                    redirect_to = folder_name + "/"  # FIXME reverse this

                if file_form.has_changed():
                    saved = file_form.save()
                    file_name = os.path.basename(saved)
                    messages.success(request, _('Uploaded new file "%s"') % file_name)

                if saved is None:
                    messages.warning(request, _("There were no changes to be saved."))

                return self.redirect(redirect_to)

        else:
            folder_form = NewFolderForm(prefix="folder", **form_kwargs)
            file_form = FileUploadForm(prefix="file", **form_kwargs)

        def _directories(d):
            fullpath = os.path.join(path or "", d, "")
            return fullpath, d, default_storage.listdir(fullpath)

        directories = [_directories(d) for d in directories]
        match = resolve(request.path)

        class FileOrFolder(AdminUrlMixin, object):
            def __init__(s, pk, name):
                s.pk = pk
                s.name = name

            def __str__(s):
                return s.name

            def __repr__(s):
                return "<%s: %s, %r>" % (s.__class__.__name__, s.name, s.urls)

            def _get_admin_namespace(s):
                return match.namespace

            def _get_url_args(s):
                return (s.pk,)

        class File(FileOrFolder):
            icon = "file"

            @cached_property
            def urls(s):
                namespace = s._get_admin_namespace()
                args = s._get_url_args()
                crud = {
                    "detail": default_storage.url(os.path.join(*args)),
                    "delete": reverse("%s:delete" % namespace, args=args),
                }
                return crud

            def _get_url_args(s):
                args = []
                if path:
                    args.append(path)
                if s.pk:
                    args.append(s.pk)
                return args

        class Folder(FileOrFolder):
            icon = "folder"

        object_list = [Folder(d[0], d[1]) for d in directories] + [
            File(f, f) for f in files
        ]
        from collections import namedtuple

        context = {
            "path": path,
            "parent": parentdir,
            "directories": directories,
            "files": files,
            "folder_form": folder_form,
            "file_form": file_form,
            "writable": writable,
            "object_list": object_list,
            "queryset": Page.objects.all(),
            "list_template": first(self.template_path("list.inc.html", "file")),
            "model": namedtuple("file", ()),
        }
        context.update(kwargs)

        templates = self.template_path("list.html", "file")
        return self.render(request, templates, context)

    @staff_login_required_m
    def rm(self, request, path=None, filename=None, *args, **kwargs):
        try:
            directories, files = default_storage.listdir(path or ".")
        except OSError as e:
            logger.exception("path: %r", path)
            raise Http404(e[1])

        class File(object):
            def __init__(self, path):
                self.path = path

            def __str__(self):
                return self.path

            def is_leaf_node(self):
                return True

        class Folder(File):
            def __init__(self, path):
                self.path = os.path.dirname(path)

            def is_leaf_node(self):
                listdir = default_storage.listdir(self.path)
                logger.debug(listdir)
                return not any([l for l in listdir if l])

        fullpath = os.path.join(path or "", filename or "")

        if filename:
            cls, action, tpl = File, default_storage.delete, "file"
            item = os.path.basename(fullpath)
        elif hasattr(default_storage, "rmdir"):
            cls, action, tpl = Folder, default_storage.rmdir, "folder"
            item = os.path.basename(os.path.dirname(fullpath))
        else:
            raise Http404(
                "We can't handle this, as the "
                "backend storage system does not "
                "support removing directories."
            )

        if path is not None:
            parentdir = os.path.normpath(os.path.join(path, "..")) + "/"
        else:
            parentdir = ""

        obj = cls(fullpath)
        if not obj.is_leaf_node():
            messages.error(request, _('The folder "%s" is not empty.') % item)
            return self.redirect(self.reverse("media:edit", kwargs={"path": parentdir}))

        if request.method == "POST":
            action(fullpath)
            messages.success(request, 'Successfully deleted %s "%s"' % (tpl, item))
            if path:
                if cls is Folder:
                    return self.redirect(
                        self.reverse("media:edit", kwargs={"path": parentdir})
                    )
                return self.redirect(self.reverse("media:edit", kwargs={"path": path}))
            return self.redirect(self.reverse("media:list"))

        context = {
            "path": path,
            "parentdir": parentdir,
            "filename": filename,
            "object": obj,
        }
        context.update(kwargs)

        templates = self.template_path("delete_confirm.html", tpl)
        return self.render(request, templates, context)
