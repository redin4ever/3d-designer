# ADR-005 — Measurement decides hard facts; the agent decides appearance

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 8.1, 8.2, 11.3, 6.3

## Decision

Two verification authorities, with a fixed split:

| Decided by measurement (non-negotiable) | Decided by the agent |
|---|---|
| manifold / watertight / self-intersection | does this look convincing |
| clipping and interpenetration | is the detail level right |
| scale and unit correctness | is the proportion pleasing |
| unapplied transforms | is this the right design choice |
| polygon budget | when is the work finished aesthetically |
| constraint satisfaction (does the rail meet the post) | |

Geometry checks **run after every geometry-changing operation** at a **user-configurable
cadence** (Gate A 3.1). They **report rather than block** by default (Gate A 6.3 — export is
allowed with a warning banner), but where measurement and agent judgement disagree on a hard
fact, **the measurement wins** (Gate A 11.3).

## Context

Gate A 8.1 and 8.2 chose agent visual judgement and agent review — both flagged at the time as
the options with adverse published measurements. Models exhibit a self-correction blind spot,
defensively justifying their own output. Agents falsely report success in 13–89% of failures
depending on model and domain, and LLM judges catch this at AUROC ≤0.65 on one benchmark and
≤0.54 on another, being "systematically misled by confident assertion language."

Gate A 1.2 set the bar at "drops into a game engine or printer." An engine agrees with the
measurement, not with the render. Wave 11.3 was asked precisely to reconcile these, and the user
chose the split above rather than either extreme.

## Consequences

- The geometry check layer is **built regardless** of whether it gates. Gate A 4.1's response
  shape ("new problems"), Gate A 6.3's export banner, and Gate A 10.3's conflict flagging all
  consume its output.
- **Definition-of-done is a re-run measurement, not a claim.** A task defined as "close every gap
  under 5mm" is done when the gap query returns zero, regardless of what any agent says.
- The agent's visual review is retained as an advisory signal on appearance — it is genuinely the
  right authority there, and it is the only authority available.
- Gating behaviour is a runtime setting, so the safer posture is one flag away if the reporting
  default proves too loose in practice.

## Superseded by

Nothing.
