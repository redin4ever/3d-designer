"""``mcp`` — the MCP server: registry policy, dispatch, both transports, image downscaling
(ADR-003).

This is the module through which everything the rest of the product builds becomes
reachable by a connected agent. Gate A 7.4, verbatim: *"also make sure it supports my
subscriptions eg: chatgpt subscription so that i can use it with it."* MCP is the only
path where a consumer subscription drives the tool with no per-token billing layered on
top, which is why both transports exist: **stdio** for Claude Desktop / Claude Code /
Cursor, **streamable HTTP** for ChatGPT developer-mode connectors.

Registry *content* — what a tool does — is declared beside each operation
(``ops.OP_SPECS``, ``export.EXPORT_SPECS``, ``raw.RAW_TOOL_SPEC``, and whatever
``measure``/``gaps``/``align``/``uv``/``detail`` eventually publish). Registry *policy* —
which of ~7 roles sees which handful of tools, how a call is validated and locked, how an
oversized render gets downscaled before it costs 15-25k tokens instead of ~1,600 — lives
here. See ``README.md`` for the full contract and ``CLAUDE.md`` for implementation status
and local conventions.

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
