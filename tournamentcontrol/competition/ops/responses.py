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


def patches(request, fragments, signals=None, redirect_to=""):
    if not is_datastar(request):
        return redirect(redirect_to)
    events = [SSE.patch_elements(html) for html in fragments]
    if signals:
        events.append(SSE.patch_signals(signals))
    return DatastarResponse(events)
