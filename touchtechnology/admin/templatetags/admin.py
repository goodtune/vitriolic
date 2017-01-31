import touchtechnology.admin
from django.template import Library

register = Library()


@register.inclusion_tag('touchtechnology/admin/_version.html',
                        takes_context=True)
def version_string(context):
    component = context.get('component')
    if component is not None:
        return {'version': component.version}
    node = context.get('node')
    if node is not None and hasattr(node.object, 'site'):
        return {'version': node.object.site(node).version}
    return {'version': touchtechnology.admin.__version__}


@register.filter
def allowed(components, request):
    """
    Given a list of components, return only those which are accessible to the
    specified user. Used to hide options from the tab-bar in the admin UI.
    """
    def show(t):
        __, module, __, instance, schemas = t

        # When django-tenant-schemas is in operation, show a component based
        # on whether it has been associated with the active schema.
        if hasattr(request, 'tenant'):
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
                permission__content_type__app_label=module):
            return True

        if request.user.groups.filter(
                permissions__content_type__app_label=module).distinct():
            return True

        # FIXME once all applications are protected, swap this for False.
        return instance.unprotected

    return [c for c in components if show(c)]
