from urllib.parse import parse_qsl, urlsplit, urlunsplit

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from touchtechnology.common.forms.tz import SelectTimezoneForm


def login(request, to, *args, **kwargs):
    scheme, netloc, path, query, fragments = urlsplit(to)
    query = dict(parse_qsl(query))
    query.update(kwargs)
    query = urlencode(query)
    to = urlunsplit((scheme, netloc, path, query, fragments))
    return redirect(to)


@require_POST
def set_timezone(request):
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
