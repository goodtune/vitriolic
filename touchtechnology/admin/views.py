from django.contrib.auth.views import LoginView

from touchtechnology.admin.branding import get_brand

FIELD_TEMPLATE = "touchtechnology/admin/templatetags/field.html"


class AdminLoginView(LoginView):
    """
    Sign in to the admin.

    Not an admin component, so the context an admin component would supply (the
    brand and the field template) is added here, keeping the page correct
    without the ``brand`` context processor.
    """

    template_name = "touchtechnology/admin/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("brand", get_brand(self.request))
        context.setdefault("field_template", FIELD_TEMPLATE)
        return context
