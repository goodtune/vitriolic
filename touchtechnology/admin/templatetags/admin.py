from urllib.parse import parse_qsl, urlencode

from django.forms import Media
from django.forms.boundfield import BoundField
from django.template import Library
from django.templatetags.static import static
from django.urls import NoReverseMatch
from django.utils.html import format_html

import touchtechnology.admin
from touchtechnology.admin.branding import get_brand
from touchtechnology.admin.explorer import build_tree

register = Library()


@register.inclusion_tag("touchtechnology/admin/_version.html", takes_context=True)
def version_string(context):
    component = context.get("component")
    if component is not None:
        return {"version": component.version}
    node = context.get("node")
    if node is not None and hasattr(node.object, "site"):
        return {"version": node.object.site(node).version}
    return {"version": touchtechnology.admin.__version__}


@register.filter
def allowed(components, request):
    """
    Given a list of components, return only those which are accessible to the
    specified user. Used to hide options from the tab-bar in the admin UI.
    """
    if components is None:
        return []

    def show(t):
        __, module, __, instance, schemas = t

        # When django-tenant-schemas is in operation, show a component based
        # on whether it has been associated with the active schema.
        if hasattr(request, "tenant"):
            if schemas is not None:
                if request.tenant.schema_name not in schemas:
                    # Warning: this is not going to protect the component from
                    # unauthorised use; it must also ensure that permissions
                    # are enforced. Superuser is *very* special and will always
                    # have permission, so do not grant this level willy-nilly.
                    return False

        if request.user.has_module_perms(module):
            return True

        if request.user.userobjectpermission_set.filter(
            permission__content_type__app_label=module
        ):
            return True

        if request.user.groups.filter(
            permissions__content_type__app_label=module
        ).distinct():
            return True

        # FIXME once all applications are protected, swap this for False.
        return instance.unprotected

    return [c for c in components if show(c)]


@register.filter
def brand_logo_url(logo):
    """
    Resolve a brand logo: absolute URLs and root-relative paths are used as
    given, anything else is looked up as a static file.
    """
    if "://" in logo or logo.startswith("/"):
        return logo
    return static(logo)


@register.simple_tag(takes_context=True)
def admin_brand(context):
    """
    The brand for the page: the one the view or the ``brand`` context processor
    supplied, otherwise resolved here from the request. Pages that bypass
    ``AdminComponentMixin.render``, such as the wizards, are therefore branded
    even when the context processor has not been configured.
    """
    if "brand" in context:
        return context["brand"]
    return get_brand(context.get("request"))


# ---------------------------------------------------------------------------
# The explorer design: icons, the tree, fields and media.

#: Other names for the admin's icons: model names and the Font Awesome names
#: components gave their menu entries before the admin drew its own.
ICON_ALIASES = {
    # Font Awesome names used by ``dropdowns()``
    "trophy": "competition",
    "shield": "club",
    "wrench": "drawformat",
    "book": "report",
    "calendar": "schoolyear",
    "sort-numeric-asc": "grade",
    "graduation-cap": "student",
    "users": "group",
    "folder-open": "image",
    "pencil-square-o": "chunk",
    "reply": "redirect",
    "puzzle-piece": "puzzle",
    "newspaper-o": "article",
    "tag": "category",
    "dashboard": "dashboard",
    # model names
    "undecidedteam": "team",
    "teamassociation": "person",
    "clubassociation": "person",
    "clubrole": "club",
    "teamrole": "team",
    "seasonmatchtime": "clock",
    "seasonexclusiondate": "ban",
    "divisionexclusiondate": "ban",
    "seasonreferee": "referee",
    "livestreamevent": "video",
    "livestreamkey": "key",
    "matchscoresheet": "image",
    "attendancerecord": "attendance",
    "sitemapnode": "page",
    "placeholder": "puzzle",
    "redirect": "redirect",
    "chunk": "chunk",
    "simplescorematchstatistic": "chart",
    "ladderentry": "ladder",
    "more": "more",
}

#: The icons the sprite has; anything else is drawn as a document.
ICONS = {
    "component", "folder", "folder-open", "item", "chevron-right",
    "chevron-left", "chevron-down", "up", "arrow-up", "arrow-down",
    "competition", "season", "division", "stage", "stagegroup", "team", "club",
    "person", "venue", "ground", "match", "clock", "ban", "referee", "video",
    "key", "drawformat", "report", "article", "category", "translation",
    "page", "sitemap", "image", "puzzle", "redirect", "chunk", "settings",
    "logout", "plus", "plus-many", "trash", "edit", "eye", "lock", "search",
    "menu", "tree", "x", "check", "more", "external", "upload", "download",
    "print", "schoolyear", "grade", "classgroup", "teacher", "student",
    "enrolment", "attendance", "assessment", "reportcard", "user", "group",
    "home", "undo", "play", "results", "allocate", "umbrella", "alert", "info",
    "link", "copy", "merge", "transfer", "refresh", "chart", "ladder", "json",
    "dashboard",
}  # fmt: skip


def icon_name(name):
    name = ICON_ALIASES.get(name, name)
    return name if name in ICONS else "item"


@register.simple_tag
def icon(name, label=""):
    """
    An icon of the admin's sprite. Without a ``label`` it is decoration and
    hidden from assistive technology; with one it is named by it.
    """
    href = "%s#%s" % (static("touchtechnology/admin/img/icons.svg"), icon_name(name))
    if label:
        return format_html(
            '<svg class="icon" role="img" aria-label="{}"><use href="{}"></use></svg>',
            label,
            href,
        )
    return format_html(
        '<svg class="icon" aria-hidden="true" focusable="false"><use href="{}"></use></svg>',
        href,
    )


@register.simple_tag(takes_context=True)
def explorer_tree(context):
    """
    The explorer for the page (see ``touchtechnology.admin.explorer``),
    worked out once per request.
    """
    request = context.get("request")
    if request is None or not getattr(request, "user", None):
        return None
    if not request.user.is_authenticated or not request.user.is_staff:
        return None
    tree = getattr(request, "_admin_explorer", None)
    if tree is None:
        admin_site = context.get("admin")
        if not hasattr(admin_site, "get_components"):
            # Imported here: the admin site imports this module.
            from touchtechnology.admin.sites import site as admin_site
        components = allowed(admin_site.get_components(), request)
        tree = build_tree(request, context, components)
        request._admin_explorer = tree
    return tree


@register.filter
def widget(bound_field, extra_class=""):
    """
    Render a form field's widget for the admin: without the public site's
    ``form-control`` class that the shared form mixin gives every widget.
    """
    if not isinstance(bound_field, BoundField):
        return bound_field
    classes = [
        c
        for c in (bound_field.field.widget.attrs.get("class") or "").split()
        if c != "form-control"
    ]
    if extra_class:
        classes.append(extra_class)
    attrs = {"class": " ".join(classes) if classes else False}
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
        attrs["aria-describedby"] = "%s-errors" % bound_field.auto_id
    elif bound_field.help_text:
        attrs["aria-describedby"] = "%s-help" % bound_field.auto_id
    return bound_field.as_widget(attrs=attrs)


#: Scripts and stylesheets that form media name and the admin serves itself.
MEDIA_REPLACEMENTS = {
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css": (
        "touchtechnology/admin/vendor/leaflet/leaflet.css"
    ),
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js": (
        "touchtechnology/admin/vendor/leaflet/leaflet.js"
    ),
}


@register.filter
def admin_media(media):
    """
    Form media as the admin loads it: what a widget would fetch from a CDN is
    served from the admin's own static files.
    """
    if not isinstance(media, Media):
        return media
    css = {
        kind: [MEDIA_REPLACEMENTS.get(path, path) for path in paths]
        for kind, paths in media._css.items()
    }
    js = [MEDIA_REPLACEMENTS.get(path, path) for path in media._js]
    return Media(css=css, js=js)


@register.filter
def initials(user):
    """One or two letters for a person with no picture."""
    name = ""
    if hasattr(user, "get_full_name"):
        name = user.get_full_name() or user.get_username()
    else:
        name = str(user)
    letters = [part[0] for part in name.replace(".", " ").split() if part]
    if not letters:
        return "?"
    if len(letters) == 1:
        return letters[0].upper()
    return (letters[0] + letters[-1]).upper()


@register.filter
def model_icon(obj):
    """The icon name of an object's, a queryset's or a manager's model."""
    model = getattr(obj, "model", None) or type(obj)
    meta = getattr(model, "_meta", None)
    return icon_name(meta.model_name) if meta else "item"


@register.filter
def admin_url(obj, name):
    """
    The admin URL of ``obj`` called ``name`` (``edit``, ``delete``...), or
    ``None`` when the object has no such page.
    """
    urls = getattr(obj, "urls", None)
    if not urls or name not in urls:
        return None
    try:
        return str(urls[name])
    except NoReverseMatch:
        return None


@register.inclusion_tag("touchtechnology/admin/_pagination.html", takes_context=True)
def admin_pagination(context):
    """The links to the other pages of a list, keeping its other parameters."""
    query = [
        (key, value)
        for key, value in parse_qsl(context.get("QUERY_STRING") or "", True)
        if key != "page"
    ]
    context.update({"QUERY_STRING": urlencode(query, True)})
    return context
