"""[User Facing] Utility views for preferences."""

from django.http import Http404, HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from touchtechnology.common.forms.tz import SelectTimezoneForm


@require_POST
def set_timezone(request):
    """Persist the selected timezone on the user session or cookie."""
    url = request.META.get("HTTP_REFERER", "/")
    response = HttpResponseRedirect(url)

    form = SelectTimezoneForm(data=request.POST)
    if form.is_valid():
        tz = form.cleaned_data["tz"]
        if hasattr(request, "session"):
            request.session["django_timezone"] = str(tz)
        else:
            response.set_cookie("django_timezone", str(tz))

    if not url_has_allowed_host_and_scheme(url, request.get_host()):
        raise Http404

    return response
