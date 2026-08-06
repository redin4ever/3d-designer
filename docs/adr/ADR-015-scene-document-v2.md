# ADR-015 — Scene document v2: constraints, joinery and acceptance persist

**Status:** accepted · **Date:** 2026-08-06 · **Source:** Gate B 1.2 · **Amends:** ADR-002, ADR-010

## Decision

`SCHEMA_VERSION` goes to `2`. `Operation.placements` (the `ConstraintSet`), `Operation.joinery`
and `Operation.acceptance` are serialised alongside the fields v1 already carried, with
`asset_class` and `proposal_id`.

A v1 file loads with an explicit, named warning stating that its operations' constraints were
never stored and that placement will not re-solve. It does not fail, and it does not load
silently.

## Context

`persistence.py` serialised nine of `Operation`'s fields and dropped the three that carry
intent. ADR-002 chose a parametric document specifically so that "move the stair, and the
railing that was constrained to its outer edge follows." That is precisely what did not survive
a save and reload: the geometry came back, the reason for it did not.

`src/scene/CLAUDE.md` recorded this honestly as "a known, documented gap" and deferred it on
the grounds that no test in the package exercised an operation carrying any of the three. That
reasoning is correct for a module built in isolation and wrong for a shipped product — the
gap is invisible until the first reload, and every file written before the fix is written
wrong.

## Consequences

- Nested dataclasses now need a serialised shape. `ConstraintSet`, `JoineryIntent` and
  `AcceptanceQuery` each get an explicit round-trip test, not an incidental one.
- The version bump is the point of the decision. Reading a v1 file without saying so would
  reproduce the original bug one layer up: a scene that looks intact and has quietly lost its
  constraints.
- `SceneDocument.load` refusing a *newer* schema than it knows stays as it was — forward
  incompatibility is still an error, backward is a warning.
- Cost of not doing this rises with every scene saved, which is why it was taken now rather
  than carried to `HANDOVER.md`.

## Superseded by

Nothing.
