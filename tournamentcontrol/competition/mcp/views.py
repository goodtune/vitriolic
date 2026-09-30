"""
Serve the competition MCP server over the Streamable HTTP transport from a
Django view.

The MCP Python SDK ships its transport as an ASGI application. Rather than
mount a second ASGI application beside Django (which would bypass Django's
middleware, sessions and authentication), the view adapts each Django
request into an ASGI request, runs it through the SDK's session manager and
turns the ASGI response back into a Django response. Every request is
served statelessly: an MCP client does not need a session, and the tools do
not keep any state between calls.
"""

from asgiref.sync import async_to_sync
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from mcp.server.transport_security import TransportSecuritySettings

from tournamentcontrol.competition.mcp import current_request, get_server


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

    def post(self, request, *args, **kwargs):
        token = current_request.set(request)
        try:
            return async_to_sync(self.handle)(request, request.body)
        finally:
            current_request.reset(token)

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
