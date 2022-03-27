from __future__ import unicode_literals

import functools
import logging
from operator import attrgetter, or_

import pytz
from django.apps import apps
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Model, Q
from django.http import Http404, HttpRequest
from django.template.loader import select_template
from first import first

from touchtechnology.common.exceptions import NotModelManager
from touchtechnology.common.mixins import NodeRelationMixin

logger = logging.getLogger(__name__)


class FauxNodeMeta(object):
    left_attr = "lft"
    right_attr = "rght"
    level_attr = "level"


class FauxNode(NodeRelationMixin):
    REPR_FMT = "<{class}: {title} ({tree_id}:{lft},{rght})>"

    def __init__(
        self,
        app,
        title,
        short_title,
        slug,
        level,
        tree_id,
        lft=None,
        rght=None,
        parent=None,
        changefreq="monthly",
        priority=0.5,
    ):
        self.app = app
        self.title = title
        self.short_title = short_title
        self.slug = slug
        self.level = level
        self.tree_id = tree_id
        self.lft = lft
        self.rght = rght
        if parent is None and app is not None:
            self.parent = app.node
        else:
            self.parent = parent

        try:
            self.changefreq = changefreq
        except AttributeError:
            logger.exception("Unable to set `changefreq` for %r", self)

        try:
            self.priority = priority
        except AttributeError:
            logger.exception("Unable to set `priority` for %r", self)

        self._mptt_meta = FauxNodeMeta()

    def __eq__(self, other):
        if other is None:
            return
        attr = ("title", "short_title", "slug", "level", "tree_id", "parent")
        gttr = [attrgetter(a) for a in attr]
        return all([g(self) == g(other) for g in gttr])

    def __repr__(self):
        attr = (
            "title",
            "short_title",
            "slug",
            "level",
            "tree_id",
            "lft",
            "rght",
            "parent",
        )
        gttr = [attrgetter(a) for a in attr]
        data = dict(zip(attr, [g(self) for g in gttr]))
        data["class"] = self.__class__.__name__
        return self.REPR_FMT.format(**data)

    @classmethod
    def equal(cls, iterable, find):
        return first(iterable, key=lambda i: i == find)

    def get_absolute_url(self):
        raise NotImplementedError

    def get_ancestors(self):
        n = self
        while n.parent:
            yield n.parent
            n = n.parent

    def get_root(self):
        if self.parent is None:
            return self
        return self.parent.get_root()


def get_mod_func(callback):
    # Converts 'touchtechnology.common.utils.get_mod_func' to
    # ['touchtechnology.common.utils', 'get_mod_func']
    try:
        dot = callback.rindex(".")
    except ValueError:
        return callback, ""
    return callback[:dot], callback[dot + 1 :]


def create_exclude_filter(queryset):
    def _filter(node):
        return Q(tree_id=node.tree_id, lft__gte=node.lft, lft__lte=node.rght)

    return functools.reduce(or_, [_filter(n) for n in queryset], Q())


def get_perms_for_model(model, add=False, change=False, delete=False, *extra):
    tpl = "%s.%%s_%s" % (model._meta.app_label, model._meta.model_name)
    res = []
    if add:
        res.append(tpl % "add")
    if change:
        res.append(tpl % "change")
    if delete:
        res.append(tpl % "delete")
    for x in extra:
        res.append(tpl % x)
    return res


def get_all_perms_for_model(model, *extra):
    return get_perms_for_model(model, True, True, True, *extra)


def tree_for_node(node):
    """
    Utility function to construct a QuerySet which has the expanded set
    of nodes for the given node.
    """
    from .models import SitemapNode

    if not isinstance(node, SitemapNode):
        real_nodes = SitemapNode.objects.filter(tree_id=node.tree_id, lft__lte=node.lft)
        node = first(real_nodes.reverse())

    if node:
        parents = node.get_ancestors()
        siblings = node.get_siblings(include_self=True)
        children = node.get_descendants()

        rest = functools.reduce(
            or_, [p.get_siblings() for p in parents], SitemapNode.objects.none()
        )

        nodes = parents | siblings | children | rest
        nodes = nodes.filter(level__lte=node.level + 1)

    else:
        nodes = SitemapNode.objects.none()

    return nodes


def model_and_manager(model_or_manager):
    """
    All our generic views work on the basis of a ``model_or_manager`` which
    needs to be unpacked into a ``model`` and ``manager``.

    The function will reduce boilerplate in generic methods.
    """
    if isinstance(model_or_manager, Model):
        model = model_or_manager._meta.model
        manager = model._default_manager
    elif hasattr(model_or_manager, "model"):
        model = model_or_manager.model
        manager = model_or_manager
    else:
        try:
            model = model_or_manager
            manager = model_or_manager._default_manager
        except AttributeError:
            raise NotModelManager(model_or_manager)
    return model, manager


def determine_page_number(request, paginator):
    """
    Determine what page number for the current request.

        request:    django.http.HttpRequest instance
        paginator:  django.core.paginator.Paginator instance
    """
    assert isinstance(request, HttpRequest)
    assert isinstance(paginator, Paginator)
    page = request.GET.get("page", 1)
    try:
        page_number = int(page)
    except ValueError:
        if page == "last":
            page_number = paginator.num_pages
        else:
            raise Http404
    return page_number


def select_template_name(templates):
    """
    Return the template name that wins template resolution for an iterable of
    template names.
    """
    try:
        # Django 1.8+
        template = select_template(templates)
        template_name = template.template.name
    except AttributeError:
        # Django 1.7
        template_name = template.name
    return template_name


def get_timezone_from_request(request):
    if hasattr(request, "session"):
        tzname = request.session.get("django_timezone", None)
        if tzname is not None:
            try:
                tzinfo = pytz.timezone(tzname)
            except pytz.UnknownTimeZoneError:
                tzinfo = None
            return tzinfo


def get_base_url(scheme="http"):
    """
    It is frustratingly difficult to obtain the appropriate base URL to use
    for sending links outside of the request-response cycle. If we are using
    the django-tenant-schemas application, this can be somewhat simplified.
    If we are not, fall back to using the django.contrib.sites framework.
    """
    if hasattr(connection, "tenant"):
        hostname = connection.tenant.domain_url
        # We have our own pattern of using the `prepend_www` attribute so lets
        # check for it and stick it on the front.
        if getattr(connection.tenant, "prepend_www", False):
            hostname = "www." + hostname
    else:
        site = apps.get_model("sites.Site").objects.get_current()
        hostname = site.domain
    context = {
        "scheme": scheme,
        "hostname": hostname,
    }
    return "%(scheme)s://%(hostname)s/" % context


def get_all_perms_for_model_cached(model, ttl=60, **extra):
    """
    Private function to cache and return the list of permissions that can be
    set on a given model.
    """
    # What are the permissions that this model accepts?
    cache_key = "model_perms.%s.%s" % (model._meta.app_label, model._meta.model_name)
    model_perms = cache.get(cache_key)
    logger.debug("model_perms_cache=%s", "MISS" if model_perms is None else "HIT")
    if model_perms is None:
        model_perms = get_all_perms_for_model(model, **extra)
        cache.set(cache_key, model_perms, timeout=ttl)
    return model_perms
