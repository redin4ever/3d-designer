# ADR-012 — A phase advances only when its acceptance queries pass, with no override

**Status:** accepted · **Date:** 2026-08-06 · **Source:** Gate B 1.1 · **Amends:** ADR-005, ADR-007

## Decision

`Orchestrator.can_promote()` evaluates the current phase's real `AcceptanceQuery` objects
against live geometry via `measure.evaluate()`. `promote()` advances only if every query
passes. **The `force=True` override is removed**, not merely discouraged.

Every failing query must return, for each failure: the object it concerns, the measured value,
the threshold it missed, and the operation that would fix it. A gate an agent cannot get
through is acceptable only if it also says how.

## Context

What shipped in pass 1 computed `passed = len(produced_this_phase) > 0` — "did this phase
record at least one non-promotion operation." `measure.evaluate()` had **zero non-test call
sites** anywhere in the product. ADR-005's "definition-of-done is a re-run measurement, not a
claim" and ADR-007's "never when an agent says it is finished" were both contradicted, and
`README.md` claimed "never because an agent said so" while nothing evaluated anything.

The user was offered four options at Gate B, including keeping the override, and chose the
strictest.

## Consequences

- **This blocks.** ADR-005's reporting posture is amended, not overturned: per-operation checks
  still report and never halt the agent. Only the phase boundary blocks.
- **It conflicts with Gate A 4.4** (fully autonomous, never stopping). An acceptance query that
  cannot be satisfied strands an unattended agent with nobody to redirect it. This was stated
  to the user at the gate and the choice was made anyway. The mitigation above — every failure
  naming its own fix — is the whole of the safety margin, which makes the quality of the
  failure message load-bearing rather than cosmetic.
- The per-phase query sets themselves become a first-class, tested surface. A query that is
  impossible to satisfy is now a product-stopping defect, not a cosmetic one.
- Combined with [ADR-013](ADR-013-role-bound-to-lease.md), the blockout → refine → detail →
  polish plan becomes enforced rather than advisory for the first time.

## Superseded by

Nothing.
