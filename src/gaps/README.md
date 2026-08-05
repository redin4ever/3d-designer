# gaps

The corrective half of `measure`. `measure` is pure and read-only — it decides what is
true about the geometry. `gaps` is the only module allowed to mutate an object in response
to what `measure` found, and it always re-runs `measure`'s own detectors afterwards to
confirm a fix actually took, rather than trusting a mutating call's own report of success.

Nine defect classes, nine different repairs (`contracts.DefectClass` docstrings are
explicit that lumping them into one "fix the gaps" step is the most common mistake in this
domain). This module addresses the ones that are mechanically fixable without design
judgement: boundary holes, duplicate/loose vertices, flipped normals, and a visual gap
between two parts. It deliberately does **not** touch `PART_CLIPPING` (needs a declared
`JoineryIntent` — a judgement call, not a mechanical fix), `UNAPPLIED_TRANSFORM`,
`SELF_INTERSECTION`, or `BUDGET_EXCEEDED` — none of those has an unambiguous "just fix it"
operation.

## Public interface

Everything importable from `gaps` is declared in `gaps/__init__.py`. Nothing else is
public; do not import `gaps.rebuild`, `gaps.tiered`, etc. directly from outside this
package.

```python
fill_boundary_holes(engine, object_id, *, max_sides=0) -> RepairOutcome
    # DefectClass.BOUNDARY_HOLE. max_sides=0 means no limit.

weld_duplicates(engine, object_id, *, tolerance=EPSILON) -> RepairOutcome
    # DefectClass.LOOSE_OR_DUPLICATE, the duplicate half.

remove_loose(engine, object_id) -> RepairOutcome
    # DefectClass.LOOSE_OR_DUPLICATE, the loose half.

fix_normals(engine, object_id) -> RepairOutcome
    # DefectClass.FLIPPED_NORMAL.

split_non_manifold(engine, object_id) -> RepairOutcome
    # DefectClass.NON_MANIFOLD_EDGE / NON_MANIFOLD_VERTEX.
    # Detection-and-report only — see CLAUDE.md for why this cannot yet repair them.

merge_shells(engine, object_id, *, max_distance) -> RepairOutcome
    # Weld vertices across an object's separate shells within max_distance.

close_visual_gap(engine, a, b, *, max_gap) -> RepairOutcome
    # DefectClass.VISUAL_GAP. Moves `a` toward `b`; `b` never moves.

repair(engine, object_id, *, classes=None) -> tuple[RepairOutcome, ...]
    # Tiered: cheapest fixes first, re-measured with `measure` between every tier.
    # classes restricts which tiers run (by DefectClass); None runs all of them.

GAPS_SPECS: tuple[ToolSpec, ...]   # roles=(ToolRole.REFINE,), every entry mutating=True
```

## Layout

| File | Owns |
|---|---|
| `primitives.py` | Thin wrappers over an existing `ModifierOps` primitive: `fill_boundary_holes`, `weld_duplicates`, `merge_shells` |
| `rebuild.py` | Repairs with no matching primitive, built by rebuilding the object from its snapshot: `remove_loose`, `fix_normals`, `split_non_manifold` |
| `visual_gap.py` | `close_visual_gap` — the one pairwise repair |
| `tiered.py` | `repair` — orchestrates the above with re-measurement between tiers |
| `registry.py` | `GAPS_SPECS` |

## Invariants

- **Every repair is verified with the matching `measure` detector, never with the repair's
  own return value.** A repair that reports success while leaving the defect in place is
  the one failure mode this module exists to prevent.
- **A repair pass on a clean object changes nothing** — not the vertex count, not the
  transform, not a single engine call. `repair()` checks a tier's detector before calling
  its repair function and skips the mutating call entirely when there is nothing to fix.
- **Every repair here is idempotent.** Running any of them twice in a row leaves the
  second run reporting `fixed=0, skipped=0` (or `skipped>0` with the same honest reason,
  for the one class this module cannot fix — see `split_non_manifold` in `CLAUDE.md`).
- **`repair()`'s outcome reflects a fresh re-measurement, never a sum of what each
  primitive claims to have done.** A tier's `RepairOutcome` is built from
  `len(before) - len(after)` against `measure`'s own detector, so a tier that only
  partially resolves its defect class reports the honest remainder in `skipped`, even
  though the underlying engine primitive it called reported success on its own terms.
- **`fixed=0, skipped=N` with a populated `reason` is how "found work and could not do
  it" is distinguished from "nothing to do".** A bare `0` cannot tell those apart —
  `fill_boundary_holes(max_sides=...)` and `close_visual_gap(max_gap=...)` both use this.

## Dependencies

`contracts` and `measure` only — `measure` for every detector this module verifies
against, never reimplemented locally (that is the seam ADR-005 draws between the two
modules). No import of `bpy`; every mutation goes through `EngineProtocol`.

## Testing

`pytest src/gaps` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact
command and known capability limits.
