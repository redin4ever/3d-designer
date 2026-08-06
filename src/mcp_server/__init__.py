"""``mcp_server`` — the MCP server: registry policy, dispatch, role-and-phase authorisation,
the session tools, both transports, image downscaling (ADR-003, ADR-013, ADR-014).

This is the module through which everything the rest of the product builds becomes
reachable by a connected agent. Gate A 7.4, verbatim: *"also make sure it supports my
subscriptions eg: chatgpt subscription so that i can use it with it."* MCP is the only
path where a consumer subscription drives the tool with no per-token billing layered on
top, which is why both transports exist: **stdio** for Claude Desktop / Claude Code /
Cursor, **streamable HTTP** for ChatGPT developer-mode connectors.

Registry *content* — what a tool does — is declared beside each operation
(``ops.OP_SPECS``, ``export.EXPORT_SPECS``, ``raw.RAW_TOOL_SPEC``, and
``measure``/``gaps``/``align``/``uv``/``detail``'s ``*_SPECS`` constants). Registry
*policy* — which of the nine roles sees which tools, which execution route each takes, how
a call is validated, authorised against the phase and locked, how an oversized render gets
downscaled before it costs 15-25k tokens instead of ~1,600 — lives here. The four session
tools (``get_phase``, ``list_objects``, ``describe_object``, ``promote_phase``) are declared
here rather than beside an operation because they report on the phase and on this registry,
and no operation module owns either. See ``README.md`` for the full contract and
``CLAUDE.md`` for implementation status and local conventions.

This file is a barrel: re-exports only, no logic.
"""

from __future__ import annotations

from .dispatch import dispatch
from .images import downscale_image
from .registry import build_registry, tools_for
from .transports import SERVER_INFO, serve_http, serve_stdio

__all__ = [
    "build_registry",
    "tools_for",
    "dispatch",
    "serve_stdio",
    "serve_http",
    "downscale_image",
    "SERVER_INFO",
]
