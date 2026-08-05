"""The two MCP transports (ADR-003) — stdio for Claude Desktop/Code/Cursor, streamable
HTTP for ChatGPT developer-mode connectors — plus ``SERVER_INFO``, the identity both
advertise.

The ``mcp`` Python SDK is an optional dependency. Importing it eagerly at module load
would make the registry and ``dispatch()`` — the part every other test in this package
exercises — unusable on a machine that has not installed it yet. Both ``serve_*``
functions import it lazily, inside the function body, and turn its absence into one
clear, named ``RuntimeError`` rather than a bare ``ModuleNotFoundError`` surfacing from
several frames deep inside someone else's package.

``SERVER_INFO`` is real, constructed data — not a stub — same reasoning as
``raw.RAW_TOOL_SPEC``: there is no implementation to defer, only a value to declare.
``serve_stdio``/``serve_http`` raise until the next pass replaces their bodies (Rule 4).
"""

from __future__ import annotations

import logging
from typing import Any

from .dispatch import dispatch
from .registry import build_registry

__all__ = ["SERVER_INFO", "serve_stdio", "serve_http"]

_LOG = logging.getLogger(__name__)

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

SERVER_INFO: dict[str, Any] = {
    "name": "blender-agent-mcp",
    "version": "0.1.0",
    "transports": ("stdio", "streamable-http"),
    "description": (
        "3D construction tools for AI agents, over MCP. stdio for Claude Desktop, "
        "Claude Code and Cursor; streamable HTTP for ChatGPT developer-mode connectors "
        "(ADR-003) — the path that lets a consumer subscription drive this tool with no "
        "per-token billing on top."
    ),
}

_SDK_MISSING = (
    "the `mcp` Python SDK is not installed (pip install mcp) — {transport} needs it to "
    "actually speak the protocol. The tool registry and dispatch() work without it; only "
    "serving a live connection over {transport} does not."
)


def _load_sdk(transport: str) -> Any:
    """Import the third-party MCP SDK lazily — never at module load — so the registry and
    ``dispatch()`` stay fully usable on a machine that has not installed it.

    NOTE for whoever wires this up against a real install: this package's own name
    (``src/mcp/``, required by this task's public interface) collides with the SDK's own
    top-level import name. Because the repo's root ``conftest.py`` puts ``src/`` first on
    ``sys.path``, ``import mcp`` from inside this very package resolves to *this* package
    (already in ``sys.modules`` under that name) rather than the installed SDK, regardless
    of install order. This function cannot fix that from inside ``src/mcp/`` — the fix
    belongs to whatever process starts the server (alias the SDK into ``sys.modules``
    under a different name before importing this package, or run it in a separate
    interpreter/venv). Flagged here, in ``README.md`` and in this task's own
    ``assumptions`` output rather than silently worked around.
    """
    try:
        import mcp.server  # the third-party MCP SDK — see the collision note above
    except ImportError as exc:
        raise RuntimeError(_SDK_MISSING.format(transport=transport)) from exc
    return mcp.server


def _build_server(sdk_server_module: Any, orchestrator: Any) -> Any:
    """Best-effort wiring onto the SDK's ``Server`` — unverified against a live install in
    this environment (the SDK is not installed here; see ``CLAUDE.md``). Exposes the full
    tool catalogue; every call still goes through ``dispatch()``, which enforces
    role-visibility and the write lock per call regardless of what the transport layer
    does. Per-role tool-set partitioning for one *live* session is a follow-up design
    decision — the MCP session model has no native "role" concept, so it likely wants one
    server process per role rather than something inferred here from a single
    ``orchestrator``.
    """
    server = sdk_server_module.Server(SERVER_INFO["name"])
    registry = build_registry()
    spec_by_name = {spec.name: (role, spec) for role, specs in registry.items() for spec in specs}

    @server.list_tools()
    async def _list_tools() -> list[dict[str, Any]]:
        return [
            {"name": spec.name, "description": spec.description, "inputSchema": spec.input_schema}
            for _role, spec in spec_by_name.values()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
        role, _spec = spec_by_name[name]
        return dispatch(name, arguments, role=role, orchestrator=orchestrator)

    return server


def serve_stdio(orchestrator: Any) -> None:
    """Run the MCP server over stdio until the client disconnects. Blocking — call from a
    script's own entry point, never from a request handler."""
    sdk = _load_sdk("stdio")
    server = _build_server(sdk, orchestrator)

    import anyio

    async def _run() -> None:
        async with sdk.stdio.stdio_server() as streams:
            await server.run(*streams, server.create_initialization_options())

    anyio.run(_run)


def serve_http(orchestrator: Any, *, host: str = "127.0.0.1", port: int = 8765) -> Any:
    """Run the MCP server over streamable HTTP. Binds loopback by default; a non-loopback
    ``host`` is a real, unauthenticated network surface reaching every registered tool —
    including unrestricted raw code execution — and must never happen silently (ADR-009).
    The warning below runs before the SDK is ever imported, so it fires even when the SDK
    is not installed.
    """
    if host not in _LOOPBACK_HOSTS:
        _LOG.warning(
            "serve_http binding to non-loopback host %r exposes every registered tool — "
            "including unrestricted raw code execution — to anything that can route to "
            "this host. There is no sandbox and no authentication layer (ADR-009).",
            host,
        )

    sdk = _load_sdk("streamable HTTP")
    server = _build_server(sdk, orchestrator)
    return sdk.streamable_http.serve(server, host=host, port=port)
