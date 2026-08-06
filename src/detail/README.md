# detail

The answer to the user's stated deal-breaker (Gate A 1.3, verbatim: *"Still looks like glued
boxes."*). Four realism passes named at Gate A 8.4 — heuristic edge treatment, surface detail
(panel lines, greebles), material realism (varied roughness, no pure black/white albedo) — plus
a report of computable proxies for what "realistic" can actually mean as a number.

Edge treatment is the highest-leverage single lever the research turned up: a perfectly sharp
CAD edge produces a hard, artificial specular break; even a tiny bevel produces the highlight
line a viewer reads as real material. But the same research warns that bevelling *uniformly* is
itself a tell (`docs/decisions/gate-A.md`, wave 8.3) — so this module's job is never "bevel
everything", it is "bevel only what would plausibly catch light".

## Public interface

Everything importable from `detail` is declared in `detail/__init__.py`. Nothing else is
public; do not import `detail.edges`, `detail.surface`, etc. directly from outside this package.

```python
@dataclass(frozen=True)
class EdgeSelection:
    edge_indices: tuple[int, ...]   # indices into MeshSnapshot.edges()
    reasons: tuple[str, ...]        # parallel to edge_indices
    rejected: int                   # candidates considered and skipped

@dataclass(frozen=True)
class DetailResult:
    object_id: str                  # object id, or material id for vary_roughness
    changed: bool                   # False means a genuine no-op, not quiet failure
    triangles_before: int
    triangles_after: int
    detail: str = ""

# edge treatment
select_bevel_edges(snapshot, *, min_dihedral_deg=30.0, convex_only=True,
                    exclude_hidden=True) -> EdgeSelection
bevel_width_for(snapshot, *, fraction=0.004, minimum=0.0005, maximum=0.01) -> float
apply_edge_treatment(engine, object_id, *, segments=2, min_dihedral_deg=30.0,
                      convex_only=True, exclude_hidden=True, fraction=0.004,
                      minimum=0.0005, maximum=0.01, cleanup=True) -> DetailResult

# bevel topology cleanup (F-018)
retriangulate_planar_regions(snapshot, *, coplanar_tolerance_deg=0.5) -> list[tuple[int,int,int]]
cleanup_bevel_topology(engine, object_id, *, coplanar_tolerance_deg=0.5) -> DetailResult

# quality metrics and the phase gate
triangle_aspect_ratios(snapshot) -> tuple[float, ...]
mean_triangle_aspect_ratio(snapshot) -> float
edge_length_uniformity(snapshot) -> float
bevel_quality_acceptance(object_id, *, ceiling=SLIVER_CEILING) -> AcceptanceQuery
SLIVER_CEILING: float

# MCP tool declarations
DETAIL_SPECS: tuple[ToolSpec, ...]

# surface detail
add_panel_lines(engine, object_id, *, spacing, depth, axis="z") -> DetailResult
add_greebles(engine, object_id, *, density, rest_fraction=0.4, seed=0) -> DetailResult

# material realism
vary_roughness(engine, material_id, *, base, spread, seed=0) -> DetailResult
clamp_albedo(rgb: tuple[float, float, float], *, metallic: bool = False) -> tuple[float, float, float]

# reporting
realism_report(engine, object_id) -> tuple[Measurement, ...]
```

## Layout

One file per responsibility, mirroring `src/measure/`'s split:

| File | Owns |
|---|---|
| `results.py` | `DetailResult` — the one result shape shared by every mutating pass |
| `edges.py` | `EdgeSelection`, `select_bevel_edges`, `bevel_width_for` — pure, no engine mutation |
| `apply.py` | `apply_edge_treatment` — the one function in the edge-treatment pairing that mutates the engine |
| `topology.py` | `retriangulate_planar_regions` — pure: which triangles should span these vertices |
| `_polygon.py` | private 2D polygon triangulation (ear clip, dynamic program, edge flips) |
| `cleanup.py` | `cleanup_bevel_topology` — the mutating half: writes the re-triangulation back |
| `quality.py` | `SLIVER_CEILING`, the aspect/uniformity metrics, `bevel_quality_acceptance` |
| `surface.py` | `add_panel_lines`, `add_greebles` |
| `materials.py` | `vary_roughness`, `clamp_albedo` |
| `report.py` | `realism_report` |
| `specs.py` | `DETAIL_SPECS` — the four MCP tool declarations for the DETAIL role |

## Invariants

- **Edge selection is a proper subset, never everything.** `select_bevel_edges` on a plain box
  must select fewer than all twelve of its edges (`edges_test.py::test_a_plain_cube_selects_a_proper_subset`).
  An implementation that returns every edge has silently reintroduced the blanket bevel Gate A
  8.3 rejected.
- **Three independent filters, each provably wired up.** Dihedral angle
  (`acos(dot(n1, n2))` in degrees), convexity (sign test against the neighbouring face's
  plane — see `edges.py`'s docstring for the exact construction and its calibration against a
  known-convex box edge), and exposure (average of the two adjacent face normals' Z component;
  negative means facing away from world up and is treated as hidden). Each filter has a test
  that shows toggling it changes the outcome — a filter that never changes anything is not
  actually implemented, whatever the code looks like.
- **Bevel width scales with object size, never fixed.** `bevel_width_for` is `fraction` of a
  characteristic size of `snapshot.world_bounds()`, clamped into `[minimum, maximum]`, always
  strictly positive. This contract deliberately does not mandate which characteristic size
  (longest axis, diagonal, cube root of volume, ...) — `edges_test.py`'s example objects are
  sized so every reasonable choice lands on the same side of both clamps.
- **The engine's unapplied-scale refusal must reach the caller.** `apply_edge_treatment` never
  catches the `EngineError` `ModifierOps.bevel_edges` raises for an object with unapplied
  non-uniform scale — bevel width is computed in object space, so an unapplied scale would
  silently produce an uneven bevel, and the engine's own refusal is the only thing standing
  between that and a shipped defect.
- **A no-op is reported as a no-op.** `apply_edge_treatment` on an object with nothing
  qualifying, and `add_greebles` with `rest_fraction=1.0`, must both report `changed=False` and
  equal before/after triangle counts — never `changed=True` about geometry that did not move.
- **Detail passes are reproducible by seed.** `add_greebles` and `vary_roughness` must produce
  identical output for the same seed and, in practice, different output for different seeds. A
  pass that cannot be reproduced cannot be reviewed or undone meaningfully.
- **Albedo is clamped, not judged.** `clamp_albedo` moves pure black and pure white inside the
  physically plausible band (non-metal ~sRGB 60-240, metal ~sRGB 180-250 per
  `contracts.MaterialOps.set_pbr`'s docstring) and leaves anything already inside it — a
  mid-grey, say — untouched. Metal and non-metal have different floors.
- **The cleanup never moves, adds or removes a vertex.** A planar region is re-triangulated
  only if it can be rebuilt from its own boundary loop, so watertightness, the silhouette and
  the vertex list are preserved *structurally* rather than by a check that happened to pass.
  A region with an interior vertex, a hole, a pinch, or a boundary over
  `MAX_REGION_BOUNDARY` vertices is declined and left exactly as found — a slightly slivery
  mesh is recoverable, a deleted vertex someone else's edge selection indexes is not.
- **The cleanup is a step, not a side effect.** `apply_edge_treatment(cleanup=False)` skips
  it, `cleanup_bevel_topology` runs it alone, and it declines (saying why) on an object that
  has been UV unwrapped or carries more than one material slot, because rebuilding the mesh
  through `MeshOps.create_mesh` cannot carry either.
- **`realism_report` never claims an overall score.** It returns only the four named,
  individually computable proxies (sharp-edge ratio, triangle aspect ratio, edge-length
  uniformity, triangle count); no published metric for "looks realistic" exists
  (`docs/research/domain.md`), and nothing in this report may be named or described as one.
  It is also read-only — it never calls a mutating `EngineProtocol` method.

## Bevel topology (F-018)

A real Blender bevel is *valid* geometry and *unacceptable* geometry at the same time. On a
stair tread (0.28 x 1.0 x 0.18 m) built as `ops.add_staircase` builds one, the raw bevel
measures a **mean triangle aspect ratio of 109.31 with a worst triangle of 1378:1**. Almost
none of that is the bevel: the engine stores every mesh triangulated
(`engine/_shared.py` invariant #1) and ear-clips the n-gons a bevel leaves behind, turning a
1 m x 0.28 m face into needles with a 0.72 mm base and two 992 mm sides — 47% of the total.

`cleanup_bevel_topology` merges coplanar triangles into regions and re-triangulates each from
its own boundary, keeping whichever of {what was there, ear clip, dynamic program, either
plus edge flips} measures best. Measured through the shipped API, against real Blender:

| object | mean aspect | worst triangle | edge-length CoV | manifold |
|---|---|---|---|---|
| stair tread 0.28x1.0x0.18 | 109.31 → **64.20** | 1378 → **324** | 1.536 → 1.603 | yes → yes |
| panel 2x2x0.1 | 312.16 → **94.09** | 4960 → **324** | 1.475 → 1.566 | yes → yes |
| cube 1 m | 146.93 → 143.86 | 460 → **325** | 1.106 → 1.102 | yes → yes |
| post 0.1x0.1x1.0 | 43.56 → 43.26 | 322 → 322 | 1.746 → 1.752 | yes → yes |

Read the *worst triangle* column, not just the mean: in every case it converges on ~324,
which is the bevel strip itself. A 4 mm strip along a 1 m edge is 250:1 by construction, and
no triangulation can improve it — only a visually wrong bevel width or a triangle-count
explosion could. **What the cleanup removes is everything worse than the bevel's own
geometry.** The cube barely moves because a cube is almost entirely bevel strip; that is why
`SLIVER_CEILING` is documented as calibrated on a tread rather than as a universal grade.

Edge-length uniformity is *reported, not promised*: it is a property of putting a 4 mm
feature on a 1 m object and moves slightly the wrong way when a re-triangulation trades one
long diagonal for another.

## Contract gap — closed

`contracts.MetricKind` now carries `SHARP_EDGE_RATIO`, `TRIANGLE_ASPECT_RATIO` and
`EDGE_LENGTH_UNIFORMITY`. `realism_report` names them directly instead of reusing
`ANGLE`/`DISTANCE`/`GAP_WIDTH` with the proxy's real name buried in `Measurement.detail`, and
`bevel_quality_acceptance` can express "this bevel is too slivery" as a real, re-runnable
`AcceptanceQuery` for the detail phase gate.

## Dependencies

`contracts` only, at import time. `.pipeline/modules.json` lists `measure` as a design-time
dependency, but nothing in this module imports it — `realism_report`'s triangle count is
computed fresh from `engine.snapshot(object_id)`, not borrowed from `measure.triangle_count`,
because `measure` is itself still a throwing stub (do not depend on it).

## Testing

`pytest src/detail` from the repo root. Almost every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required.

The one exception is `bevel_quality_test.py`, marked `needs_blender` and skipped when `bpy`
is not importable. It has to be: `FakeEngine.bevel_edges` never moves a vertex (it duplicates
a face to model polygon growth), so a bevel-quality assertion written against the fake proves
nothing at all. The defect it pins down only exists in real geometry. See `CLAUDE.md`.
