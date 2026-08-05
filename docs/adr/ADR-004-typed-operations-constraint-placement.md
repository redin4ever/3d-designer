# ADR-004 — Typed parametric operations, constraint-first placement

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 3.3, 3.4

## Decision

Agents act through a curated library of **typed parametric operations** with named, validated
parameters — `add_railing(path, height, baluster_gap, posts_plumb)` — not primitives
(`add_cube`, `move`, `rotate`) and not whole-object composites (`build("a staircase")`).

Placement is expressed as **declarative constraints** the tool solves — `follows`, `offset`,
`ends_at`, `flush_with`, `plumb`, `spacing` — with **raw coordinates available as an escape
hatch** for cases the vocabulary cannot express.

## Context

Both extremes are measured to be worse. SheetCopilot measured −12.6% Exec@1 and −6.1% Pass@1
collapsing a task into a single high-level call: the call's own parameter surface became too
complex to use reliably. At the other end, primitive-level actions destabilise decision-making
over long horizons — a railing takes ~140 of them and drift accumulates across every one, with
nothing in the system knowing "this is a railing" and therefore nothing able to check it as one.

On placement, the numbers are stark: SpatialVLM — a model *trained specifically* for spatial
estimation — lands within 2× of ground truth 37.2% of the time. LayoutGPT/NSR-1K, emitting
numeric constraints resolved by a solver, measures 91–95%. Holodeck uses the same shape with 10
predefined soft-constraint types and a DFS solver enforcing hard constraints absolutely.

## Consequences

- Every operation's parameters are **validated on entry and re-measurable on exit**. This is what
  makes ADR-005's programmatic definition-of-done possible: the acceptance check re-runs the same
  query the parameter defined.
- Constraints are **stored, not just applied** (ADR-002), so they survive and re-solve when
  something they depend on moves.
- The escape hatch is a real risk: two code paths, and agents reach for the easy one under
  pressure. Mitigated by making the constraint path the documented default, keeping raw
  coordinates out of the tool descriptions' primary examples, and recording escape-hatch use in
  the operation log so it is visible rather than silent.
- Growing the library is the main ongoing product work. Each operation must be authored, validated
  and given an acceptance query — this is deliberate; it is the thing that makes the output not
  look like glued boxes.

## Superseded by

Nothing.
