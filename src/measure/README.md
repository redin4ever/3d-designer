# measure

The single authority on what is true about the geometry. Computes the 7 metric queries and
detects the 10 defect classes in `contracts.DefectClass`. **Pure** — it reads, it never
mutates. Repair lives in `gaps`, not here.

ADR-005 splits verification authority in two: measurement decides hard facts (manifold,
clipping, scale, transforms, budget, constraint satisfaction), the agent decides appearance.
This module is the entire measurement half. Vision models score 34-56% where humans score
79-99% on exactly the spatial judgements this module answers instead — every function here
replaces a guess with a computed number.

## Public interface

Everything importable from `measure` is declared in `measure/__init__.py`. Nothing else is
public; do not import `measure.metrics`, `measure.topology`, etc. directly from outside this
package.

```python
# metrics — each returns a contracts.Measurement
bounds(engine, object_id)
dimensions(engine, object_id)                  # (x, y, z) metres
distance(engine, a, b)                         # 0 if touching/overlapping, never negative
angle_between(engine, a, b)                    # degrees, between dominant axes
gap_width(engine, a, b)                        # 0 if touching/overlapping
volume(engine, object_id)
triangle_count(engine, object_id)

# defect detection — each returns tuple[contracts.Defect, ...]
find_boundary_holes(engine, object_id)
find_non_manifold_edges(engine, object_id)
find_non_manifold_vertices(engine, object_id)
find_loose_or_duplicate(engine, object_id, tolerance=EPSILON)
find_flipped_normals(engine, object_id)
find_self_intersections(engine, object_id)
find_unapplied_transforms(engine, object_id)
find_clipping(engine, pairs, joinery=())       # pairs: Sequence[tuple[str, str]]
find_visual_gaps(engine, pairs, max_gap)

# composition
inspect(engine, object_id) -> tuple[Defect, ...]                  # every single-object check
report(engine, scope, pairs=(), joinery=(), full_scene=False) -> MeasurementReport
evaluate(engine, query: AcceptanceQuery) -> AcceptanceResult
is_watertight(engine, object_id) -> bool
```

## Layout

One file per responsibility, so two agents extending different checks never touch the same
file:

| File | Owns |
|---|---|
| `metrics.py` | The 7 metric queries |
| `topology.py` | The 6 single-object defect finders (holes, non-manifold edge/vertex, loose/duplicate, flipped normal, unapplied transform) |
| `intersections.py` | Self-intersection, clipping, visual gaps — everything that needs a BVH-pruned pair or a full triangle-triangle test |
| `report.py` | `inspect`, `report`, `evaluate`, `is_watertight` — composes the above into what the rest of the system consumes |

## Invariants

- **Pure.** No function in this module calls a mutating `EngineProtocol` method
  (`set_transform`, `apply_transform`, `join`, anything on `ModifierOps`, …). Only
  `snapshot`, `world_bounds`, `list_objects`, `exists`. Verified directly:
  `report_test.py::test_measure_never_mutates_the_engine`.
- **`distance` and `gap_width` are never negative.** 0 means touching or overlapping, not a
  penetration depth — that number belongs to `find_clipping`'s `magnitude`, and only there,
  because non-convex mesh-mesh penetration depth is unsolved in the general case (ADR-011).
- **Clipping is not inferred, it is declared.** `find_clipping` treats an overlap as a defect
  unless a `contracts.JoineryIntent` in its `joinery` argument explicitly permits it
  (`JoineryIntent.permits`). No amount of geometric analysis can distinguish a post socketed
  50mm into a deck from two posts wrongly overlapping by 50mm — both are identical BVH
  overlaps of identical magnitude.
- **`report()` cannot claim a scope it did not examine.** `contracts.MeasurementReport`
  enforces this at construction — a defect or measurement naming an object outside the
  declared `scope` raises. `report()` must therefore widen its returned scope to include
  every object it genuinely touched, including ones reached only through `pairs`.
- **A defect's severity always comes from `contracts.DEFAULT_SEVERITY`.** Two code paths must
  never assign different severities to the same defect class.
- **`evaluate()` is the definition-of-done mechanism (ADR-005).** It re-runs the query
  against live geometry every time; it is never told the answer by a caller and never trusts
  a prior result.

## Dependencies

`contracts` only. `find_clipping` and `find_visual_gaps` accept `pairs` as a plain
`Sequence[tuple[str, str]]` — normally produced by `spatial.pairs_overlapping(engine)` — so
this module has no import-time dependency on `spatial` even though `.pipeline/modules.json`
lists it as a design-time one.

## Testing

`pytest src/measure` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact command
and the local test-file layout.
