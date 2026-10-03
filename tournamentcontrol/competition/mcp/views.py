"""
Serve the competition MCP servers over the Streamable HTTP transport from
Django views.

The MCP Python SDK ships its transport as an ASGI application. Rather than
mount a second ASGI application beside Django (which would bypass Django's
middleware, sessions and authentication), the view adapts each Django
request into an ASGI request, runs it through the SDK's session manager and
turns the ASGI response back into a Django response. Every request is
served statelessly: an MCP client does not need a session, and the tools do
not keep any state between calls.

Authentication
--------------
A client identifies itself the way any other HTTP client of the site does.
A Django session cookie is recognised by ``AuthenticationMiddleware`` as
usual. A ``Bearer`` token in the ``Authorization`` header is handed to the
configured authentication backends through ``django.contrib.auth.authenticate``
so a backend that understands OAuth 2.0 access tokens (for example
``oauth2_provider.backends.OAuth2Backend`` from django-oauth-toolkit) can
turn it into ``request.user``. The public endpoint serves anonymous clients;
the administration endpoint requires a staff user and otherwise answers
with the ``401`` challenge that lets an MCP client discover how to obtain a
token (RFC 9728).
"""

import json
import logging

from asgiref.sync import async_to_sync
from django.contrib.auth import authenticate
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from mcp.server.transport_security import TransportSecuritySettings

from tournamentcontrol.competition.mcp import (
    ToolCall,
    current_request,
    current_tool_call,
    get_server,
    redact_arguments,
)
from tournamentcontrol.competition.mcp.admin import get_admin_server
from tournamentcontrol.competition.mcp.signals import mcp_request_handled

LOG = logging.getLogger(__name__)


def _json(content):
    """``content`` decoded as JSON, or ``None`` if it is not JSON."""
    try:
        return json.loads(content)
    except ValueError:
        return None


def bearer_token(request):
    """The bearer token presented in the ``Authorization`` header, if any."""
    scheme, __, token = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


@method_decorator(csrf_exempt, name="dispatch")
class MCPView(View):
    """
    The Streamable HTTP endpoint of the competition MCP server.

    Only ``POST`` reaches the SDK. In the Streamable HTTP transport ``GET``
    opens the server-to-client event stream and ``DELETE`` ends a session;
    a stateless server has no use for either, and a synchronous WSGI worker
    cannot hold a stream open (it would hang until the worker is killed).
    The specification lets a server answer both with 405, which Django's
    ``View`` does for any method left out of ``http_method_names``.

    ``server`` may be given to ``as_view`` to serve a specific ``MCPServer``;
    by default the one built from the project settings is used. Django's
    ``ALLOWED_HOSTS`` already guards against DNS rebinding, so the SDK's own
    host check is disabled.
    """

    http_method_names = ["post", "options"]
    server = None
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )

    def get_server(self):
        return self.server or get_server()

    def authenticate(self, request):
        """
        Identify a client presenting a bearer token.

        The session (if any) has already been resolved by the authentication
        middleware; a bearer token is only consulted for a caller that is
        otherwise anonymous. ``authenticate`` offers the request to every
        configured backend, so whichever backend recognises the token (an
        OAuth 2.0 provider such as django-oauth-toolkit) supplies the user.
        """
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return
        if bearer_token(request) is None:
            return
        user = authenticate(request=request)
        if user is not None:
            request.user = user

    def check_access(self, request):
        """
        Decide whether ``request.user`` may use the server. Return ``None``
        to allow the call, or the ``HttpResponse`` to send instead.
        """
        return None

    def post(self, request, *args, **kwargs):
        self.authenticate(request)
        refusal = self.check_access(request)
        if refusal is not None:
            return refusal
        call = ToolCall()
        request_token = current_request.set(request)
        call_token = current_tool_call.set(call)
        try:
            response = async_to_sync(self.handle)(request, request.body)
        finally:
            current_tool_call.reset(call_token)
            current_request.reset(request_token)
        self.request_handled(request, response, call)
        return response

    def request_handled(self, request, response, call):
        """Send ``mcp_request_handled`` describing the request just answered."""
        message = _json(request.body)
        method = message.get("method") if isinstance(message, dict) else None
        tool = arguments = None
        if method == "tools/call" and isinstance(message.get("params"), dict):
            tool = message["params"].get("name")
            arguments = redact_arguments(
                self.get_server(), tool, message["params"].get("arguments")
            )
        if call.exception is not None:
            error = type(call.exception).__name__
        else:
            answer = _json(response.content)
            if not isinstance(answer, dict):
                error = None
            elif "error" in answer:
                error = "jsonrpc"
            elif isinstance(answer.get("result"), dict) and answer["result"].get(
                "isError"
            ):
                error = "isError"
            else:
                error = None
        for receiver, result in mcp_request_handled.send_robust(
            sender=self.__class__,
            request=request,
            method=method,
            tool=tool,
            arguments=arguments,
            duration=call.duration,
            error=error,
        ):
            if isinstance(result, Exception):
                LOG.error(
                    "mcp_request_handled receiver %r failed",
                    receiver,
                    exc_info=result,
                )

    async def handle(self, request, body):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "scheme": request.scheme,
            "path": request.path,
            "raw_path": request.get_full_path().encode("utf-8"),
            "query_string": request.META.get("QUERY_STRING", "").encode("latin-1"),
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in request.headers.items()
                if key.lower() != "content-length"
            ]
            + [(b"content-length", str(len(body)).encode("latin-1"))],
            "client": (request.META.get("REMOTE_ADDR"), 0),
            "server": (request.get_host(), request.get_port()),
        }

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        status = 500
        headers = []
        chunks = []

        async def send(message):
            nonlocal status, headers
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        # The SDK's session manager can only be started once, so in
        # stateless mode a fresh one is built for every request. Building
        # the Starlette application is the public way to get one.
        server = self.get_server()
        server.streamable_http_app(
            json_response=True,
            stateless_http=True,
            transport_security=self.transport_security,
        )
        manager = server.session_manager
        async with manager.run():
            await manager.handle_request(scope, receive, send)

        response = HttpResponse(b"".join(chunks), status=status)
        for key, value in headers:
            response[key.decode("latin-1")] = value.decode("latin-1")
        return response


class AdminMCPView(MCPView):
    """
    The Streamable HTTP endpoint of the competition *administration* MCP
    server, which is only served to staff users.

    An anonymous caller is answered with ``401 Unauthorized`` carrying a
    ``WWW-Authenticate: Bearer`` challenge whose ``resource_metadata``
    parameter points at the protected resource metadata document for this
    endpoint (RFC 9728 §5.1). MCP clients such as Claude Code read that
    document to find the authorization server, register themselves and run
    the OAuth 2.1 authorization code flow in the browser, then retry with a
    bearer token. A caller who is authenticated but not an active staff
    user is refused with ``403 Forbidden``; the tools themselves apply the
    same model and object permissions as the admin site.
    """

    def get_server(self):
        return self.server or get_admin_server()

    def resource_metadata_url(self, request):
        """
        Where the protected resource metadata for this endpoint is published:
        the RFC 9728 path form, ``/.well-known/oauth-protected-resource``
        followed by the path of the endpoint, on this site.
        """
        return request.build_absolute_uri(
            "/.well-known/oauth-protected-resource" + request.path
        )

    def check_access(self, request):
        user = request.user
        if not user.is_authenticated:
            if bearer_token(request) is None:
                challenge = 'Bearer resource_metadata="%s"'
                description = (
                    "Authentication is required. Obtain an access token from "
                    "the authorization server named in the protected "
                    "resource metadata and present it as a bearer token."
                )
            else:
                challenge = 'Bearer error="invalid_token", resource_metadata="%s"'
                description = "The bearer token is invalid or has expired."
            response = JsonResponse(
                {"error": "unauthorized", "error_description": description},
                status=401,
            )
            response["WWW-Authenticate"] = challenge % self.resource_metadata_url(
                request
            )
            return response
        if not (user.is_active and user.is_staff):
            return JsonResponse(
                {
                    "error": "forbidden",
                    "error_description": (
                        "The competition administration tools are only "
                        "available to staff users."
                    ),
                },
                status=403,
            )
        return None
