# ADR-014 — Export executes through its tool handler, outside the operation log

**Status:** accepted · **Date:** 2026-08-06 · **Source:** Gate B 4.1 · **Amends:** ADR-002

## Decision

`export_scene` and `check_export_budget` carry a real `ToolSpec.handler` callable. `dispatch`
invokes it directly against the engine and returns its result. They are **not** operation kinds,
do not append to the operation log, and do not participate in undo.

## Context

Both were registered as MCP tools with no handler behind them. `dispatch` wrapped any
handler-less mutating tool into an `Operation` and routed it through `orchestrator.perform()`,
which requires the kind to be present in the handler registry — and export never was. Verified
live against real Blender: `dispatch("export_scene", ...)` raised
`KeyError: "unknown operation kind 'export_scene'"`.

`src/app/app_test.py:66` — the test written specifically to catch "a tool an agent can see but
nothing can execute" — carved both names out of its own assertion with no comment. That is how
this survived a green suite, a green gate, and two QA rounds.

The `ToolSpec.handler` field already existed with a documented purpose ("so a future module
that does attach a handler does not need `dispatch.py` touched at all") and an unused code
path in `dispatch`. This decision uses what was already built for it.

## Consequences

- The operation log stays a log of things that changed geometry. An export produces no
  geometry, so an entry for it would be an entry undo could only treat as a no-op.
- Export is not undoable, which is correct: the file is already on disk.
- An operator watching the action log will not see exports there. The export banner
  (Gate A 6.3) remains the user-facing signal, and the viewer's `EXPORT_REPORT` message —
  handled in the frontend and never sent — is the right channel for it.
- The carve-out in `app_test.py` is removed, and the "every registered tool is executable"
  assertion becomes total. A test that excludes the case it exists to catch is worse than no
  test, and this is the second time that pattern has produced a P0 here.

## Superseded by

Nothing.
