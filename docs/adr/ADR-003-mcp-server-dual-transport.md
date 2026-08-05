# ADR-003 — MCP server over both stdio and streamable HTTP

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 9.1, 11.2, 7.4

## Decision

The tool is exposed as an **MCP server** supporting **both** transports:

- **stdio** — for Claude Desktop, Claude Code, Cursor and any local MCP client.
- **streamable HTTP** — for ChatGPT developer-mode connectors, which require a reachable endpoint.

Both transports serve the same tool registry over shared core code.

## Context

Gate A 7.4, verbatim: *"also make sure it supports my subscriptions eg: chatgpt subscription so
that i can use it with it."* This is the requirement. MCP is the only path where a consumer
subscription drives the tool — an API-key integration would bill per token on top of a
subscription the user already pays for.

MCP protocol version 2025-11-25 is current. Standalone HTTP+SSE is deprecated; SSE as an upgrade
*within* streamable HTTP is not.

## Consequences

- **Tool count is capped.** Chance-corrected analysis puts the accuracy-optimal visible tool set
  at K≈2.3–7.4; RAG-MCP measured selection accuracy at 13.62% with a large undifferentiated set.
  Past ~30 tools, description overlap causes agents to invent tool names and borrow argument
  schemas from the wrong tool. The registry is therefore **role-partitioned**: each sub-agent role
  sees 5–8 tools, never the full library. This is load-bearing, not a nicety.
- **Never return images through MCP `ImageContent` without checking the client.** Several clients
  pass the base64 payload through as text at 15–25k tokens per image instead of ~1,600 — a 10–20×
  tax. Renders go back downscaled (≤1024px long edge, ≈1,334 tokens) and the transport is verified
  per client.
- Two transports means two integration test paths. They share the tool registry and handlers, so
  the divergent surface is small.
- The HTTP transport listens locally by default. It is a network surface on the user's machine and
  is documented as such in `docs/SECURITY.md` alongside ADR-009.

## Superseded by

Nothing.
