import logging
import operator
import os
import re
import socket
from decimal import Decimal
from itertools import islice, zip_longest
from urllib.parse import parse_qsl

import pkg_resources
from classytags.arguments import Argument
from classytags.core import Options
from classytags.helpers import AsTag
from django.conf import settings
from django.db.models import Model, Q
from django.db.models.query import QuerySet
from django.forms.boundfield import BoundField
from django.forms.widgets import (
    CheckboxInput,
    CheckboxSelectMultiple,
    Input,
    MultiWidget,
    RadioSelect,
    Select,
    Textarea,
)
from django.template.base import Node
from django.template.library import Library
from django.template.loader import get_template, render_to_string
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from guardian.core import ObjectPermissionChecker
from namedentities import named_entities

from touchtechnology.common.default_settings import CURRENCY_SYMBOL
from touchtechnology.common.exceptions import NotModelManager
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.utils import (
    create_exclude_filter,
    get_all_perms_for_model_cached,
    model_and_manager,
    tree_for_node,
)
from tournamentcontrol.competition.utils import FauxQueryset

logger = logging.getLogger(__name__)

camel_case_re = re.compile(r"(?P<new_word>((?<![A-Z])[A-Z]|[A-Z](?![A-Z0-9])))")

version_re = re.compile(
    r"""^
    (?P<version>\d+\.\d+)         # minimum 'N.N'
    (?P<extraversion>(?:\.\d+)*)  # any number of extra '.N' segments
    (?:
        (?P<prerel>[abc]|rc)         # 'a' = alpha, 'b' = beta
                                     # 'c' or 'rc' = release candidate
        (?P<prerelversion>\d+(?:\.\d+)*)
    )?
    (?P<postdev>(\.post(?P<post>\d+))?(\.dev(?P<dev>\d+))?)?
    $""",
    re.VERBOSE,
)

FORM_FIELD_TEMPLATE = get_template("touchtechnology/common/templatetags/field.html")

register = Library()


@register.filter
def at_a_time(i, n):
    """
    Turn a list into smaller lists of n items. For example, if we have:

        object_list = [1, 2, 3, 4, 5, 6, 7, 8]

    The {% object_list|at_a_time:2 %} will result in:

        [[1, 2], [3, 4], [5, 6], [7, 8]

    Or {% object_list|at_a_time:3 %} will result in:

        [[1, 2, 3], [4, 5, 6], [7, 8, None]]

    We don't filter out None items, so check when iterating in your template.
    """
    return zip_longest(*[islice(i, x, None, n) for x in range(n)])


@register.filter
def camel_case_to_underscores(s):
    """Converts a CamelCase name to use lowercase_and_underscores.

    e.g. "ConvertHTMLToText" -> "convert_html_to_text"
    """

    def convert(match):
        content = match.group().lower()
        if match.start() == 0:
            return content
        else:
            return "_%s" % content

    return camel_case_re.sub(convert, s).lower()


@register.filter
def camel_case_split(s):
    """Converts a CamelCase name to be split by spaces.

    e.g. "CovertHTMLToText" -> "Convert HTML To Text"
    """

    def convert(match):
        content = match.group()
        if match.start() == 0:
            return content
        else:
            return " %s" % content

    return camel_case_re.sub(convert, s)


@register.filter
def cssify(s):
    return slugify(s or "").replace("-", "_")


@register.filter
def future(d):
    if d > timezone.now():
        return True
    return False


@register.filter
def split(st, on):
    return st.split(on)


@register.filter
def twittify(s):
    twitter_re = re.compile(r"(@(?P<username>[a-z0-9_]+)?)", re.I)
    return mark_safe(
        twitter_re.sub(
            r'@<a class="twitter user" '
            'target="_blank" '
            'href="http://twitter.com/\\2">\\2</a>',
            s,
        )
    )


@register.filter
def count(queryset):
    return queryset.count()


@register.filter
def disabled(queryset):
    return queryset.exclude(enabled=True)


@register.filter
def enabled(queryset):
    return queryset.filter(enabled=True)


@register.filter
def invisible(queryset):
    return queryset.exclude(hidden_from_navigation=False)


@register.filter
def visible(queryset):
    return queryset.filter(hidden_from_navigation=False)


@register.tag
def navigation(parser, token):
    """
    Build a navigational structure.

        Examples:

        {% navigation %}
        {% navigation current_node=node %}
        {% navigation start_at=1 stop_at=3 %}
        {% navigation root='page_3' %}
    """
    args = token.split_contents()[1:]
    kwargs = {k: parser.compile_filter(v) for k, v in [a.split("=", 1) for a in args]}
    return NavigationNode(kwargs)


class NavigationNode(Node):
    def __init__(self, kwargs):
        self.kwargs = kwargs

    def render(self, context):
        r_kwargs = dict(
            [
                (str(k), v.resolve(context, ignore_failures=True))
                for k, v in self.kwargs.items()
            ]
        )
        return do_navigation(**r_kwargs)


def do_navigation(
    root=None,
    start_at=None,
    stop_at=None,
    current_node=None,
    expand_all_nodes=None,
    template_name=None,
    **kwargs,
):
    nodes = SitemapNode._tree_manager.select_related("content_type", "parent")

    if template_name is None:
        template_name = "touchtechnology/common/templatetags/navigation.html"

    if expand_all_nodes is None:
        expand_all_nodes = False

    logger.debug("======== do_navigation ========")
    logger.debug("template_name: %r", template_name)
    logger.debug("expand_all_nodes: %r", expand_all_nodes)
    logger.debug("current_node: %r", current_node)

    if root is not None:
        if isinstance(root, str):
            try:
                root = resolve(root).kwargs.get("node")
            except Resolver404:
                root = resolve(reverse(root)).kwargs.get("node")

        logger.debug("root: %r", root)

        try:
            nodes = root.get_descendants(include_self=True)
        except AttributeError:
            nodes = SitemapNode.objects.none()

        if (
            current_node is not None
            and current_node.tree_id == root.tree_id
            and root.lft < current_node.lft
            and not expand_all_nodes
        ):
            nodes = tree_for_node(current_node)

    elif current_node is not None and not expand_all_nodes:
        nodes = tree_for_node(current_node)

    logger.debug("nodes: %r", nodes)

    # make sure we hide any nodes that are in a hidden part of the tree
    nodes_hidden_from_navigation = nodes.filter(
        Q(hidden_from_navigation=True) | Q(enabled=False)
    )

    hidden_from_navigation = create_exclude_filter(nodes_hidden_from_navigation)

    nodes = nodes.exclude(hidden_from_navigation)

    logger.debug("nodes[cleaned]: %r", nodes)

    # flatten the list of nodes to a list
    tree = list(nodes)

    if current_node is None and not expand_all_nodes:
        stop_at = max(start_at or 0, stop_at or 0, 0)

    if start_at is not None:
        tree = [n for n in tree if n.level >= start_at]

    if stop_at is not None:
        tree = [n for n in tree if n.level <= stop_at]

    if not expand_all_nodes and current_node is not None:
        parents = []
        n = current_node
        while n.parent is not None:
            parents.append(n.parent)
            n = n.parent

        fmt = "[{rel}] {url} {node}"

        def func(node):
            """
            Filter function to determine if a node should appear in the
            navigation tree or not.
            """
            rel = current_node.rel(node)
            url = node.get_absolute_url()
            logger.debug(fmt.format(node=node, rel=rel, url=url))
            return rel in {
                "ROOT",
                "ANCESTOR",
                "PARENT",
                "UNCLE",
                "ME",
                "SIBLING",
                "DESCENDANT",
            }

        log = {
            "rel": "NODE",
            "node": repr(current_node),
            "url": current_node.get_absolute_url(),
        }
        logger.debug(fmt.format(**log))
        tree = [t for t in tree if func(t)]

    # re-sort the queryset to get our correct tree structure back
    tree = sorted(tree, key=operator.attrgetter("tree_id", "lft"))

    context = {
        "nodes": tree,
        "current_node": current_node,
        "hidden_nodes": nodes_hidden_from_navigation,
        "start_at": start_at,
        "stop_at": stop_at,
    }

    return render_to_string(template_name, context)


@register.simple_tag
def field(bf, label=None):
    if not isinstance(bf, BoundField):
        raise TypeError(
            "{{% field %}} tag can only be used with " "BoundFields ({0})".format(bf)
        )

    if bf.is_hidden:
        return smart_str(bf)

    widget = bf.field.widget
    widget_class_name = camel_case_to_underscores(widget.__class__.__name__)

    if label is None:
        label = bf.label

    if isinstance(widget, (CheckboxInput,)):
        radio_checkbox_input = True
    else:
        radio_checkbox_input = False

    if label:
        if isinstance(widget, (Input, Select, Textarea),) and not isinstance(
            widget, (CheckboxInput, RadioSelect, CheckboxSelectMultiple, MultiWidget)
        ):
            # Use a <label> tag
            caption = bf.label_tag(label, attrs={"class": "field_name"})
        else:
            # Don't use a <label> tag
            label_suffix = bf.form.label_suffix or ""
            caption = f'<span class="field_name">{label}{label_suffix}</span>'
    else:
        caption = ""

    context = {
        "f": bf,
        "caption": caption,
        "widget_class_name": widget_class_name,
        "radio_checkbox_input": radio_checkbox_input,
        "no_label": not bool(label),
    }

    return FORM_FIELD_TEMPLATE.render(context)


@register.inclusion_tag("touchtechnology/common/templatetags/analytics.html")
def analytics(code=None):
    if code is None:
        code = getattr(settings, "GOOGLE_ANALYTICS", code)
    context = {
        "code": code,
        "debug": not os.environ.get("SITE_ENV", "dev") == "live",
    }
    return context


@register.inclusion_tag(
    "touchtechnology/common/templatetags/pagination.html", takes_context=True
)
def pagination(context):
    query_string = context.get("QUERY_STRING", "")
    query = parse_qsl(query_string, True)
    query = [q for q in query if q[0] != "page"]
    query_string = urlencode(query, True)
    context.update({"QUERY_STRING": query_string})
    return context


@register.filter("type")
def get_type(obj):
    if isinstance(obj, QuerySet):
        return obj.model._meta.verbose_name
    elif isinstance(obj, Model):
        return obj._meta.verbose_name
    else:
        return obj.__class__.__name__


@register.filter("types")
def get_type_plural(obj):
    if isinstance(obj, (QuerySet, FauxQueryset)):
        return obj.model._meta.verbose_name_plural
    elif isinstance(obj, Model):
        return obj._meta.verbose_name_plural
    else:
        # extremely naive
        return obj.__class__.__name__ + "s"


@register.filter
def htmlentities(s):
    replaced_entities = named_entities(
        escape(s).encode("ascii", "xmlcharrefreplace").decode("utf8")
    )
    return mark_safe(replaced_entities)


@register.filter("abs")
def absolute_value(value):
    return abs(value)


@register.inclusion_tag("touchtechnology/common/templatetags/price.html")
def price(value, extra=""):
    context = {
        "SYMBOL": CURRENCY_SYMBOL,
        "AMOUNT": value or Decimal("0.00"),
        "EXTRA": extra,
    }
    return context


@register.filter("islice", is_safe=True)
def islice_(value, arg):
    """
    Returns an iterator slice of the list.
    """
    try:
        bits = []
        for x in arg.split(":"):
            if len(x) == 0:
                bits.append(None)
            else:
                bits.append(int(x))
        return islice(value, *bits)

    except (ValueError, TypeError):
        return value  # Fail silently.


@register.inclusion_tag("touchtechnology/common/templatetags/version.html")
def version(package, url=None):
    environment = pkg_resources.Environment()
    context = {}
    try:
        if package == "python":
            context = {
                "name": "Python",
                "project": "Python",
                "version": environment.python,
                "release": None,
            }
        else:
            distribution = environment[package][-1]
            release = version_re.match(distribution.version).groupdict()
            context = {
                "name": distribution.key,
                "project": distribution.project_name,
                "version": distribution.version,
                "release": release.get("prerel"),
            }
    except IndexError:
        logger.exception(
            'Attempting to lookup version for package "%s" not ' "in pkg_resources",
            package,
        )
    if url:
        context["url"] = url
    return context


@register.filter("permchecker")
def create_permission_checker(model_or_manager, user):
    """
    Create an :class:`ObjectPermissionChecker` for optimal permission checking
    of related objects.

    http://django-guardian.readthedocs.io/en/stable/userguide/performance.html
    """
    model, manager = model_and_manager(model_or_manager)
    checker = ObjectPermissionChecker(user)
    try:
        checker.prefetch_perms(manager)
    except UnboundLocalError:
        logger.exception(
            "https://github.com/django-guardian/django-guardian/issues/519"
        )
    return checker


@register.filter("checkperm")
def check_permission(obj, checker):
    """
    For a given model instance and a :class:`ObjectPermissionChecker` return
    which permissions the associated user has.
    """
    return [
        model_perm
        for model_perm in get_all_perms_for_model_cached(obj._meta.model)
        if checker.has_perm(model_perm, obj)
    ]


@register.filter("hasperm")
def has_permission(obj, user):
    try:
        model, manager = model_and_manager(obj)
    except NotModelManager:
        logger.exception('error="model cannot be determined"')
        return set()

    logger.debug(
        'model="%s.%s", object_id="%s", user="%s"',
        model._meta.app_label,
        model._meta.model_name,
        getattr(obj, "pk", ""),
        user.get_username(),
    )

    # Calculate the permissions this user has for the given object, both
    # directly and inferred by group memberships.
    perms = user.get_all_permissions(obj)
    perms |= user.get_group_permissions(obj)

    # What are the permissions that this model accepts?
    model_perms = get_all_perms_for_model_cached(model, ttl=300)

    # Superusers have all permissions, so add each permission that the model
    # accepts for this user to the set that has been explicitly cast.
    if user.is_superuser:
        perms.update(model_perms)

    # Otherwise we need to iterate the groups that the user belongs to and see
    # if they transfer permission to the user.
    else:
        for group in user.groups.all():
            group_perms = group.permissions.all()
            group_model_perms = [p.codename for p in model_perms if p in group_perms]
            logger.debug(
                'user="%s", group="%s", permissions="%s"',
                user.get_username(),
                group,
                ", ".join(group_model_perms),
            )
            perms.update(group_model_perms)

    # Log the resulting set of permissions for this user for this object.
    logger.debug('user="%s", permissions=%r', user.get_username(), perms)

    return perms


@register.simple_tag
def host():
    return socket.gethostname()


@register.inclusion_tag("touchtechnology/common/templatetags/hostname.html")
def hostname():
    hostname = socket.gethostname()
    host, domain = hostname.split(".", 1)
    return dict(hostname=hostname, host=host, domain=domain)


class Login(AsTag):
    options = Options("as", Argument("varname", required=False, resolve=False))

    def get_value(self, context):
        request = context.get("request")
        url = reverse("accounts:login")
        if request:
            url += "?next=" + request.path
        return url


register.tag(Login)
