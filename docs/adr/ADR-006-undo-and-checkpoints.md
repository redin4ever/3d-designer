# ADR-006 — Per-action undo and named checkpoints via the operation log

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 4.3, 5.4

## Decision

Undo is implemented as a **pointer into the operation log**, not as scene snapshots. Undoing N
actions truncates the log to `head - N` and re-evaluates. Named checkpoints are named pointers.
The operator can **pause a running build, roll back N steps, and redirect in words** (Gate A 5.4).

## Context

ADR-002 makes the scene a deterministic function of an ordered operation list, which makes this
the cheap implementation rather than the expensive one. Snapshotting mesh state per action at
thousands of objects (Gate A 11.4) would be prohibitive; moving a pointer is free.

No surveyed tool has this. The de-facto standard agent–Blender bridge tells users in its README
to save their work manually before letting the agent run — undo is the operator's job. Gate A 1.3
named breaking existing work as an abandonment trigger.

## Consequences

- **Re-evaluation cost is the constraint**, not storage. Mitigated by caching evaluated geometry
  per operation so only operations downstream of the truncation point re-run.
- Raw code execution (ADR-009) and any opaque mesh edit are **not replayable**, so they act as
  barriers in the log: undo across one is a snapshot restore, not a replay. This is recorded
  explicitly at the barrier so the cost is visible.
- Pause must be cooperative — checked between operations, never mid-operation — so the log is
  never truncated to a half-applied state.

## Superseded by

Nothing.
