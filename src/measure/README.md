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

# neighbour-scoped pairwise checks — the caller supplies ids, not pairs
neighbour_pairs(engine, object_ids, *, margin=0.0, index=None) -> tuple[tuple[str, str], ...]
neighbour_defects(engine, object_ids, *, joinery=(), max_gap=0.005, margin=0.0, index=None)

# composition
inspect(engine, object_id) -> tuple[Defect, ...]                  # every single-object check
report(engine, scope, pairs=(), joinery=(), full_scene=False) -> MeasurementReport
evaluate(engine, query: AcceptanceQuery) -> AcceptanceResult
is_watertight(engine, object_id) -> bool

# the MCP tool surface
MEASURE_SPECS: tuple[ToolSpec, ...]   # 6 tools, ToolRole.INSPECT, all mutating=False
bind_engine(engine | None) -> None    # composition-root fallback; dispatch supplies its own
```

### The six tools

| Tool | Answers |
|---|---|
| `measure_distance(a, b)` | closest surface-to-surface distance, metres |
| `measure_gap(a, b)` | shortest empty span, metres |
| `measure_angle(a, b)` | degrees between the two long axes |
| `measure_dimensions(object_ids)` | size, bounds, volume and triangle count per object |
| `find_clipping(object_ids, joinery, margin)` | parts interpenetrating where they should not |
| `defect_report(object_ids, include_neighbours, joinery, max_gap)` | every defect class, scoped |

Six, not sixteen: ADR-003 puts the accuracy-optimal visible set at about 5-8 per role, and
`ToolRole.INSPECT` also carries `mcp_server`'s three session tools. The seven single-object
metrics are grouped into one tool and the ten defect classes into another, rather than
published one apiece.

Every handler returns a `contracts.MeasurementReport`, including the ones that answer with a
single number — one return type is what lets `mcp_server.serialize` render any of them
without duck-typing. Every parameter's schema carries its unit in its own description; an
agent acts on the schema without reading source, and a review found an undescribed scalar
being guessed as `[x, y, z]`.

## Layout

One file per responsibility, so two agents extending different checks never touch the same
file:

| File | Owns |
|---|---|
| `metrics.py` | The 7 metric queries |
| `topology.py` | The 6 single-object defect finders (holes, non-manifold edge/vertex, loose/duplicate, flipped normal, unapplied transform) |
| `intersections.py` | Self-intersection, clipping, visual gaps — everything that needs a BVH-pruned pair or a full triangle-triangle test |
| `report.py` | `inspect`, `report`, `evaluate`, `is_watertight` — composes the above into what the rest of the system consumes |
| `neighbours.py` | `neighbour_pairs`, `neighbour_defects` — the pairwise checks scoped through `spatial.SpatialIndex` |
| `registry.py` | `MEASURE_SPECS` — the tool declarations and their schemas |
| `_broadphase.py` | the uniform grid over one mesh's triangles that keeps `find_self_intersections` sub-quadratic |
| `_handlers.py` | the callables behind `MEASURE_SPECS`, and how they reach the live engine |
| `_errors.py` | `measure.unknown_object` and friends — a rule and a *usable* next step |

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

- **The self-intersection check prunes work, never findings.** `_broadphase.candidate_pairs`
  returns a *superset* of the pairs whose boxes overlap, and two triangles that intersect
  necessarily have overlapping boxes — so the answer is identical to the all-pairs sweep it
  replaced. Every fallback in that file falls back to *more* work. It matters because the
  check is a `BLOCKER` and it runs automatically: on a real Blender 960-triangle sphere it
  went from 6.5s finding nothing to 0.02s finding nothing, and the interpenetrating case
  (two joined spheres, 1920 triangles) still reports all 126 crossings.
- **A failure names a rule and a *usable* next step.** `measure.unknown_object` suggests up
  to five near-miss ids, never the whole scene. At the thousands of objects ADR-011 targets,
  listing every id is a next step no agent can act on.

## Dependencies

`contracts` and `spatial` — the latter only for the neighbour-scoped queries in
`neighbours.py`, which is what `spatial.SpatialIndex` was built for. `find_clipping` and
`find_visual_gaps` still accept `pairs` as a plain `Sequence[tuple[str, str]]`, so the
low-level checks carry no dependency on it.

Nothing here imports `mcp_server`: `ARCHITECTURE.md`'s arrow runs `scene -> orchestration ->
mcp`, and `mcp_server.registry` imports *this* module. The one thing `_handlers.py` needs
from it — the attribute `context.needs("engine")` sets, so `dispatch` hands a handler the
live engine — is written as a literal, with `bind_engine` as the fallback if it ever
changes.

## Testing

`pytest src/measure` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact command
and the local test-file layout.
