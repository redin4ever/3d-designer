# ADR-008 — Python 3.13 core with in-process `bpy`; static three.js frontend

**Status:** accepted · **Date:** 2026-08-05 · **Source:** derived from Gate A 9.1, 9.2, 5.1, 11.2

## Decision

- **Backend: Python 3.13.14**, with `bpy` 5.2.0 **imported in-process**. Verified working:
  `import bpy` → `5.2.0 LTS`, live `bpy.data` access, no Blender subprocess required.
- **MCP server: Python**, official SDK, both transports (ADR-003).
- **Frontend: a static three.js page** served by the backend, fed by WebSocket.
- **Node v24.18.0** is used only for frontend tooling and the Puppeteer test suite — it is not in
  the runtime path.

## Context

This was not a gate question; it is derived. Gate A 9.2 put Blender in the core and 11.1 approved
installing the toolchain, which was then verified working. Given `bpy` is a Python module, a
Python backend removes an entire process boundary.

The alternative — a Node orchestrator talking to a Python Blender worker — was the research
recommendation *while the machine had no Python*. That constraint is gone. Keeping it would mean
two runtimes, a serialisation boundary on every geometry call, and two test frameworks, bought
for nothing.

In-process `bpy` matters at Gate A 11.4's scale (thousands of objects): scene state stays live in
memory across calls instead of being re-marshalled per operation.

## Consequences

- **`bpy`-as-a-module has no `bpy.context.window`** — a stricter subset than `blender --background`.
  Anything needing a window (certain operators, OpenGL viewport renders) must go out to a real
  Blender subprocess. That path exists as a fallback but is not the default.
- **`bpy` is locked to exactly Python 3.13.** A future Blender release will re-lock to a newer
  minor and force a coordinated interpreter upgrade. Pinned and documented.
- One test framework (`pytest`) for the backend, one (Puppeteer) for the frontend. Both runnable
  on this machine today — which was Gate A 9.4's requirement.
- The frontend stays a static page with no build-time server dependency, so the Puppeteer suite
  can drive it against a fixture backend without booting Blender.

## Superseded by

Nothing.
