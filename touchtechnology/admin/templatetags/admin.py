from django.template import Library
from django.templatetags.static import static

import touchtechnology.admin
from touchtechnology.admin.branding import get_brand

register = Library()


@register.simple_tag(takes_context=True)
def version_string(context):
    component = context.get("component")
    if component is not None:
        return component.version
    node = context.get("node")
    if node is not None and hasattr(node.object, "site"):
        return node.object.site(node).version
    return touchtechnology.admin.__version__


def _app_labels_granted(request):
    """
    The applications ``request.user`` holds a permission in, over one object
    or through a group: asked of the database once for the request, however
    many components the menu weighs and however often the page asks.
    """
    labels = getattr(request, "_admin_app_labels", None)
    if labels is None:
        user = request.user
        objects = user.userobjectpermission_set.values_list(
            "permission__content_type__app_label", flat=True
        )
        groups = user.groups.values_list(
            "permissions__content_type__app_label", flat=True
        )
        labels = request._admin_app_labels = set(objects.union(groups))
    return labels


@register.filter
def allowed(components, request):
    """
    Given a list of components, return only those which are accessible to the
    specified user. Used to hide options from the admin's menu, and their
    widgets from its home page (``AdminSite.dashboard``).
    """
    if components is None:
        return []

    # Nothing is shown to a visitor the admin does not know: the pages the
    # shell draws for them (an error page, say) have an empty navigation. Nor
    # may we ask an anonymous user for object permissions, they have none.
    if not request.user.is_authenticated:
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

        if module in _app_labels_granted(request):
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
