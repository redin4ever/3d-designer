"""The two MCP transports (ADR-003) — stdio for Claude Desktop/Code/Cursor, streamable
HTTP for ChatGPT developer-mode connectors — plus ``SERVER_INFO``, the identity both
advertise.

Two transports rather than one because they reach different customers: stdio is what a
local editor spawns as a subprocess, and streamable HTTP is what a hosted connector dials.
Gate A 7.4, verbatim: *"also make sure it supports my subscriptions eg: chatgpt subscription
so that i can use it with it."* Both run the **same** server object from
:mod:`mcp_server.sdk_bridge`, so there is one tool catalogue and one set of rules, not two
that can drift.

This file owns transport *policy* — the identity, where it binds, and the ADR-009 warning.
Everything about the SDK's shape lives in ``sdk_bridge``; the split is what kept the last
SDK-version break to one file.

The SDK is imported lazily, inside each ``serve_*``, so the registry and ``dispatch()``
stay fully usable on a machine that has not installed it. That is most of this repository's
test suite.
"""

from __future__ import annotations

import logging
import asyncio
import contextlib
from typing import Any

from .sdk_bridge import build_server, load_sdk

__all__ = ["SERVER_INFO", "serve_stdio", "serve_http", "http_app"]

_LOG = logging.getLogger(__name__)

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

DEFAULT_HTTP_PORT = 8765
DEFAULT_HTTP_PATH = "/mcp"

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


def _warn_if_exposed(host: str, *, expose_raw: bool = False) -> None:
    """ADR-009 in one line, before anything binds.

    Gate A 7.2 chose unrestricted arbitrary code execution for connected agents and 7.4
    chose unrestricted filesystem access, both with the risk stated in the option text. On
    loopback the trust boundary is the user's own machine, which is what makes that a
    reasonable trade. Off loopback it is whoever can route to the port, and the same choice
    is a different decision entirely — so it is never made silently.

    Deliberately fires before the SDK is imported, so an operator who mistypes ``--host``
    is told even on a machine where the server cannot start at all.
    """
    if host not in _LOOPBACK_HOSTS:
        capability = (
            "including explicitly enabled unrestricted raw code execution and full "
            "filesystem access"
            if expose_raw
            else "including scene-mutating semantic operations"
        )
        _LOG.warning(
            "serve_http binding to non-loopback host %r exposes every discovered tool — "
            "%s — to anything that can route to this host. There is no authentication "
            "layer (ADR-009).",
            host, capability,
        )


def serve_stdio(orchestrator: Any, *, expose_raw: bool = False) -> None:
    """Run the MCP server over stdio until the client disconnects.

    Blocking — call it from a process's own entry point (``python -m mcp_server``), never
    from a request handler.

    While this is serving, the SDK points file descriptor 1 at stderr and serves the wire
    from a private duplicate, so a stray ``print`` — or Blender's own C-level chatter during
    an export — misses the JSON-RPC stream instead of corrupting it. Nothing protects the
    *startup* that happens before this call, which is why ``__main__`` diverts stdout for
    the duration of engine construction.
    """
    sdk = load_sdk("stdio")
    server = build_server(
        sdk, orchestrator, name=SERVER_INFO["name"], version=SERVER_INFO["version"],
        expose_raw=expose_raw,
    )

    import anyio

    async def _run() -> None:
        async with sdk.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(_run)


def http_app(
    orchestrator: Any,
    *,
    host: str = "127.0.0.1",
    path: str = DEFAULT_HTTP_PATH,
    json_response: bool = False,
    expose_raw: bool = False,
) -> Any:
    """The streamable-HTTP endpoint as a plain ASGI application, bound to nothing.

    Separate from :func:`serve_http` so the app can be mounted inside someone else's ASGI
    server — a hosted connector behind their own TLS and auth — and so it can be built and
    inspected without starting a listener. ``serve_http`` is then just this plus uvicorn.

    On a loopback host the SDK enables DNS-rebinding protection by itself: without it, a web
    page the user visits could reach this port through their browser, and every tool here
    runs arbitrary code (ADR-009).
    """
    _warn_if_exposed(host, expose_raw=expose_raw)
    sdk = load_sdk("streamable HTTP")
    server = build_server(
        sdk, orchestrator, name=SERVER_INFO["name"], version=SERVER_INFO["version"],
        expose_raw=expose_raw,
    )
    return server.streamable_http_app(
        streamable_http_path=path, host=host, json_response=json_response,
    )


def serve_http(
    orchestrator: Any,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_HTTP_PORT,
    path: str = DEFAULT_HTTP_PATH,
    maintenance: Any = None,
    expose_raw: bool = False,
) -> None:
    """Run the MCP server over streamable HTTP until interrupted. Blocking.

    Binds loopback by default; see :func:`_warn_if_exposed` for what a non-loopback host
    actually means here.
    """
    app = http_app(orchestrator, host=host, path=path, expose_raw=expose_raw)

    import uvicorn

    if maintenance is None:
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    async def run_with_maintenance() -> None:
        server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))

        async def maintain() -> None:
            while not server.should_exit:
                maintenance()
                await asyncio.sleep(0.01)

        task = asyncio.create_task(maintain())
        try:
            await server.serve()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(run_with_maintenance())
