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


@register.filter
def allowed(components, request):
    """
    Given a list of components, return only those which are accessible to the
    specified user. Used to hide options from the tab-bar in the admin UI.
    """
    if components is None:
        return []

    # Nothing is shown to a visitor the admin does not know: the pages the
    # shell draws for them (an error page, say) have an empty navigation. Nor
    # may we ask an anonymous user for object permissions, they have none.
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
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
