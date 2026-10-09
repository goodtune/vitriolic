"""
Answer a request either as HTML (plain browser) or as a Datastar SSE
response that patches elements by id (the page's JavaScript).
"""

from datastar_py.django import (
    DatastarResponse, ServerSentEventGenerator as SSE,
)
from django.http import HttpResponse
from django.shortcuts import redirect


def is_datastar(request):
    return request.headers.get("Datastar-Request") == "true"


def fragment_response(request, html):
    if is_datastar(request):
        return DatastarResponse(SSE.patch_elements(html))
    return HttpResponse(html)


def patches(request, fragments, signals=None, redirect_to="", page=None):
    """
    Answer a change either as Datastar patches or, for a plain browser, with
    a redirect to ``redirect_to``.

    A refusal the user must read cannot be redirected away from, so the view
    passes ``page``: a callable returning the full page (status 200) to send
    a plain browser instead. ``fragments`` may also be a callable, so a plain
    browser's request does not render what only Datastar would use.
    """
    if not is_datastar(request):
        if page is not None:
            return page()
        return redirect(redirect_to)
    if callable(fragments):
        fragments = fragments()
    events = [SSE.patch_elements(html) for html in fragments]
    if signals:
        events.append(SSE.patch_signals(signals))
    return DatastarResponse(events)
