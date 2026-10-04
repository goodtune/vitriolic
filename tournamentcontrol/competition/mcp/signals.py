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
#:     here too), otherwise ``None``. Arguments a tool marks with
#:     ``sensitive_arguments`` (free text that may name a person, secrets)
#:     have their value replaced by ``"[redacted]"``.
#: ``duration``
#:     Seconds spent running the tool, or ``None`` if it did not run (another
#:     method, an unknown tool, or arguments that failed validation).
#: ``error``
#:     ``None`` if the request succeeded. Otherwise, following the
#:     OpenTelemetry semantic conventions for MCP (``error.type``): the class
#:     name of the exception the tool raised; ``"tool_error"`` for a tool
#:     result the SDK marked as an error without the tool raising (arguments
#:     that failed validation, an unknown tool); or the JSON-RPC error code,
#:     as a string, of an error response. Codes for a request the caller got
#:     wrong (``-32700``, ``-32600``, ``-32601``, ``-32602``, ``-32002``) are
#:     not errors of the server and leave ``error`` as ``None``.
#: ``status_code``
#:     The JSON-RPC error code of an error response, as a string (the
#:     conventions' ``rpc.response.status_code``), whether or not it counts as
#:     an error; ``None`` for a successful response.
#:
#: A tool that fails still answers with HTTP 200, so ``error`` is the only
#: place the failure shows. Receivers run in the request thread after the
#: response is built; an exception in one is logged and does not affect the
#: response.
mcp_request_handled = Signal()
