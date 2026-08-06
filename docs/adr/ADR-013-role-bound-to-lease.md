# ADR-013 — Role is bound to the lease and checked against the phase

**Status:** accepted · **Date:** 2026-08-06 · **Source:** Gate B 6.3 · **Amends:** ADR-003, ADR-007

## Decision

An agent no longer declares its own role per call. `Orchestrator.acquire()` grants a role
alongside the write lease; `dispatch` reads the role from the lease and ignores any role the
caller passes. A call to a tool the granted role does not hold, or to a tool not legal in the
session's current phase, is refused with a named rule that states the current phase and what
is available in it.

Read-only (`INSPECT`) access does not require a write lease, and is granted its own
lease-less token so many readers can still run concurrently per ADR-007.

## Context

Measured in Phase 6 against the real product: `dispatch` checked only that the requested tool
was visible to the role string **the caller itself supplied**, and never compared that to
`self.phase`. Calling a POLISH tool (`unwrap_uvs`) and a REFINE tool (`add_railing`) while the
session had never left `blockout` both succeeded silently. Any agent could claim any role.

The staged plan the user chose at Gate A 3.2 was therefore advisory in the strictest sense:
nothing anywhere enforced ordering, and `Orchestrator.tools_for()` — the method a phase-aware
"what can I do now" query would call — returned 16 tool names that do not exist.

## Consequences

- The phase split becomes enforced. Together with [ADR-012](ADR-012-phase-promotion-is-a-hard-gate.md)
  this is the first point at which "blockout, then refine, then detail, then polish" constrains
  anything.
- **This is not a security boundary.** ADR-009 gives every connected agent arbitrary code
  execution and full disk access by explicit user choice; a role check does not and cannot
  contain that. This is a correctness and coordination mechanism, and any documentation
  implying otherwise is wrong.
- A refusal must name the phase, the tool, the role that would allow it, and how to promote —
  otherwise an agent loops on the same call, which is exactly the failure Gate A 4.2 was
  asked about.
- `Orchestrator.tools_for()` now delegates to the real registry (Gate B 4.4), so "what can I
  do now" and "what will actually be accepted" are the same answer for the first time.

## Superseded by

Nothing.
