# ADR-009 — Unrestricted code execution and unrestricted filesystem access

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 7.2, 7.4, 7.1, 7.3

## Decision

The tool exposes an **unrestricted code-execution capability** to connected agents, and places
**no restriction on which filesystem paths** an agent may read or write. Both were chosen
explicitly by the user with the risk stated in the question.

## Context

Gate A 7.2 offered three options; the option text named the concrete precedent — the de-facto
standard agent–Blender bridge exposes exactly this design and carries an open CVSS 9.0
remote-code-execution issue as a result — and the user chose unrestricted anyway. Gate A 7.4 chose
"anywhere on disk" over a project-scoped sandbox.

The mitigating context is real, not rhetorical: Gate A 7.1 puts the tool on the user's own
machine, and 7.3 keeps the codebase private and undistributed. The trust boundary is a single
user's own machine and their own agents. There is no multi-tenant surface and no third party whose
data is at stake.

## Consequences

- **The tool provides no security boundary against a connected agent.** An agent that can call it
  can run arbitrary code as the user and touch any file the user can. This is stated plainly in
  `docs/SECURITY.md` and in the tool's own README, not buried.
- **The HTTP transport (ADR-003) is the sharp edge.** stdio is only reachable by a process the
  user launched; an HTTP listener is reachable by anything that can route to it. It binds to
  loopback by default, and binding to a non-loopback address requires an explicit flag that logs a
  warning naming this ADR.
- Raw execution **breaks the parametric chain** (ADR-002) and acts as an undo barrier (ADR-006).
  Every raw call is recorded in the operation log as an opaque edit so the cost is visible rather
  than discovered later.
- This ADR is the one most worth revisiting if the product ever stops being private and local.
  Gate A 7.3 changing is the trigger; nothing else here holds without it.

## Superseded by

Nothing.
