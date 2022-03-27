import logging
from collections import OrderedDict
from itertools import zip_longest

from django import template
from django.db import models
from django.template import loader
from django.urls import resolve, reverse_lazy
from guardian.shortcuts import get_objects_for_user

from touchtechnology.common.utils import (
    get_all_perms_for_model_cached,
    model_and_manager,
)

logger = logging.getLogger(__name__)
register = template.Library()


@register.inclusion_tag("mvp/list.html", takes_context=True)
def mvp_list(context, queryset, scope=None, template=None):
    model, manager = model_and_manager(queryset)

    request = context.get("request")
    component = context.get("component")

    if scope is None:
        scope = model._meta.model_name

    # Use the template_path resolution method of the AdminComponent to find
    # the right list for inclusion. Use "list.inc.html" by default because
    # "list.html" is reserved for use by generic_list view.
    if template is None:
        paths = component.template_path("list.inc.html", model._meta.model_name)
        # Ensure there is a sensible default so we always find something
        paths.append("mvp/list.inc.html")
        logger.debug("template_search=%r", paths)
        template = loader.select_template(paths)
        template_name = template.template.name
        logger.debug("template_search_result=%r", template_name)

    match = resolve(request.path)
    namespace = match.namespace
    if match.namespace.rsplit(":", 1)[1] != scope:
        namespace = "%s:%s" % (match.namespace, scope)

    perms = get_all_perms_for_model_cached(model)
    global_perms = any([request.user.has_perm(p) for p in perms])

    # If the user does not have any global permissions then adjust the
    # queryset to return only the objects they can act on.
    if not global_perms:
        queryset = get_objects_for_user(
            request.user,
            perms,
            queryset.select_related(),
            use_groups=True,
            any_perm=True,
        )

    # Tidy up the kwargs found using resolve
    kw = match.kwargs.copy()
    kw.pop("admin", None)
    kw.pop("component", None)

    context.update(
        {
            "model": model,
            "template": template,
            "queryset": queryset,
            "object_list": queryset,
            "create": reverse_lazy("%s:add" % namespace, kwargs=kw),
            # Pass to template the name permissions so we can re-use template
            # code to generically list and add/change/delete objects
            "add_perm": "%s.add_%s" % (model._meta.app_label, model._meta.model_name),
            "view_perm": "%s.view_%s" % (model._meta.app_label, model._meta.model_name),
            "change_perm": "%s.change_%s"
            % (model._meta.app_label, model._meta.model_name),
            "delete_perm": "%s.delete_%s"
            % (model._meta.app_label, model._meta.model_name),
        }
    )
    return context


@register.filter
def related(instance, whitelist=None):
    rel = OrderedDict()

    if whitelist is not None:
        rel = OrderedDict(zip_longest([w for w in whitelist if w], []))

    related_objects = [
        f
        for f in instance._meta.get_fields()
        if (f.one_to_many or f.one_to_one) and f.auto_created
    ]

    for ro in related_objects:
        skip_log = 'filter="related", field="%s", reason="%s"'
        try:
            name = ro.get_accessor_name()
        except AttributeError as e:
            logger.debug(skip_log, name, e)
            continue

        if whitelist is not None and name not in rel:
            logger.debug(skip_log, name, "not in whitelist")
            continue

        if isinstance(ro.field, models.ManyToManyField):
            logger.debug(skip_log, name, "m2m")
            continue

        rel[name] = getattr(instance, name)

    # improve performance of related queries
    related = getattr(instance, "_mvp_related", {})
    annotate = getattr(instance, "_mvp_annotate", {})
    select_related = getattr(instance, "_mvp_select_related", {})
    only = getattr(instance, "_mvp_only", {})

    for name, manager in rel.items():
        # Prioritise fully customised queries. If you take this route, you're
        # on your own - make sure all the fields you will use are returned.
        if name in related:
            manager = related[name]
        # Alternatively perform simple select_related and/or annotations.
        else:
            if name in select_related:
                manager = manager.select_related(*select_related[name])
            if name in annotate:
                manager = manager.annotate(**annotate[name])
            if name in only:
                manager = manager.only(*only[name])
        yield (manager, name)


@register.filter
def mvp_list_template(manager, table=None):
    """
    When looping through a list of "related" managers we may need to use an
    alternative template file.

    We'll need to pass in a mapping of manager's to template names.

    :param manager: a model manager
    :param table: a dictionary of model class to template name
    :returns: template path or None
    """
    if table is None:
        table = {}
    return table.get(manager.model)
