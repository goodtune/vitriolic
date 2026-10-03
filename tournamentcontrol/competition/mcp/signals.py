from django.dispatch import Signal

#: Sent by ``views.MCPView`` once it has answered an MCP request, so a project
#: can log or count how its MCP servers are used. ``sender`` is the view class
#: and the keyword arguments are:
#:
#: ``request``
#:     The Django request.
#: ``method``
#:     The JSON-RPC method (``initialize``, ``tools/list``, ``tools/call``...),
#:     or ``None`` when the body is not a single JSON-RPC request.
#: ``tool``
#:     The name of the tool asked for by a ``tools/call``, otherwise ``None``.
#: ``arguments``
#:     The arguments of that ``tools/call`` exactly as the client sent them,
#:     before the SDK validated them (so arguments that failed validation are
#:     here too), otherwise ``None``. They are whatever the caller typed and
#:     can include personal details, so take care where they are written.
#: ``duration``
#:     Seconds spent running the tool, or ``None`` if it did not run (another
#:     method, an unknown tool, or arguments that failed validation).
#: ``error``
#:     ``None`` if the request succeeded. Otherwise the class name of the
#:     exception the tool raised; ``"isError"`` for a tool result the SDK
#:     marked as an error without the tool raising (arguments that failed
#:     validation, an unknown tool); or ``"jsonrpc"`` for a JSON-RPC error.
#:
#: A tool that fails still answers with HTTP 200, so ``error`` is the only
#: place the failure shows. Receivers run in the request thread after the
#: response is built; an exception in one is logged and does not affect the
#: response.
mcp_request_handled = Signal()
