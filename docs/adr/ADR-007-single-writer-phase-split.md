# ADR-007 — One writer, many readers, split by phase

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 10.1, 10.2, 10.3, 3.2

## Decision

Sub-agents split **by phase** — blockout → refine → detail → polish — with one phase active at a
time. Within a phase, **many sub-agents may read, measure, critique and propose in parallel;
exactly one applies changes**. Collisions are **flagged with the exact geometry involved**, like a
merge conflict, never silently resolved.

## Context

A live 3D scene is a single shared mutable resource. That is structurally the case where parallel
LLM writers are measured to fail: Cognition's argument names conflicting implicit decisions on
shared state as fundamental rather than incidental, and their counterexample is subagents writing
to a shared codebase concurrently. Anthropic's +90.2% multi-agent result came from subagents doing
independent read-only research with nothing shared to conflict over, merged once by a single
writer — and cost ~15× the tokens of a single chat.

Both sides converge on the same shape for shared mutable state: parallel readers, one writer, or
fully isolated copies merged explicitly. Gate A 10.1 chose the former.

Phase splitting (Gate A 10.2) has near-zero collision risk *by construction* — mutual exclusion
falls out of the sequence — and it is the same structure as the staged plan chosen in Gate A 3.2,
so phase gating does double duty as concurrency control.

## Consequences

- Sub-agent roles get **role-partitioned toolsets** (ADR-003): the detail-phase agent sees bevel,
  greeble and panel-line tools, not the blockout primitives.
- Parallelism is real but confined to analysis. Wall-clock gains come from many simultaneous
  measurements and proposals, not from simultaneous edits.
- **Phase promotion needs a criterion.** A phase hands off when its acceptance queries pass
  (ADR-005), not when an agent says it is finished.
- Cost scales with the reader fan-out. Reader agents are cheap (read-only, small toolsets, short
  contexts) but they are not free, and a fan-out budget per phase is required.
- Figma-style last-writer-wins was explicitly rejected: it works for design properties because two
  people rarely touch the same one, but for geometry (move a wall while another agent attaches a
  railing to it) a silent overwrite produces an invalid model, not just a surprise.

## Superseded by

Nothing.
