from __future__ import unicode_literals

import pytz
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.http import is_safe_url, urlencode
from django.utils.six.moves.urllib.parse import parse_qsl, urlsplit, urlunsplit
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
    url = request.META.get('HTTP_REFERER', '/')
    response = HttpResponseRedirect(url)

    form = SelectTimezoneForm(data=request.POST)
    if form.is_valid():
        tzname = form.cleaned_data.get('timezone')
        if tzname in pytz.all_timezones_set:
            if hasattr(request, 'session'):
                request.session['django_timezone'] = tzname
            else:
                response.set_cookie('django_timezone', tzname)

    if not is_safe_url(url=url, host=request.get_host()):
        raise Http404

    return response
