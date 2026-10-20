from django.conf import settings
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url

from touchtechnology.admin.branding import get_brand

FIELD_TEMPLATE = "touchtechnology/admin/templatetags/field.html"


class AdminLoginView(LoginView):
    """
    Sign in to the admin.

    Not an admin component, so the context an admin component would supply (the
    brand and the field template) is added here, keeping the page correct
    without the ``brand`` context processor.

    Only a signed-in *staff* user is sent on to ``next``. Anyone else signed in
    cannot use the admin, and the admin sends them here, so redirecting them on
    would loop; they get the form with a notice and may sign in as someone else.
    """

    template_name = "touchtechnology/admin/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.method == "GET" and request.user.is_staff:
            url = self.get_success_url()
            if url == request.path:
                url = resolve_url(settings.LOGIN_REDIRECT_URL)
            return HttpResponseRedirect(url)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("brand", get_brand(self.request))
        context.setdefault("field_template", FIELD_TEMPLATE)
        user = self.request.user
        if user.is_authenticated and not user.is_staff:
            context["signed_in_as"] = user.get_username()
        return context
