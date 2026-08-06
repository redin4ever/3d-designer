# measure — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Every function here is implemented and its suite passes. This module was built
test-first (Rule 4): the tests were written against the contract, run, and confirmed failing
on `NotImplementedError` before any body existed.

What changed in the Gate B pass, and what it replaced:

- **`MEASURE_SPECS` exists** (F-006, Gate B 3.1). This module published *zero* MCP tool
  specs: `mcp_server.registry._load_optional("measure", "MEASURE_SPECS")` collected `()`, so
  no connected agent could ask for a distance, a gap, an angle, a clipping check or a defect
  report. Everything was implemented, tested, green and unreachable.
- **`find_self_intersections` is no longer O(triangles²)** (F-015, Gate B 5.1). Measured
  against real Blender: a 960-triangle sphere took **6.5s** and found nothing, on a check
  that runs automatically after every geometry change — ~40% of a realistic 33-second
  session, on the first non-trivial object anyone builds. It now takes **0.02s** on the same
  mesh, through the uniform grid in `_broadphase.py`.
- **`neighbour_defects` exists.** `inspect` runs the single-object checks only and says so,
  so the two defects a person actually notices — parts driven into each other, joints that
  should meet and do not — were reachable only by a caller that already knew which pairs to
  ask about. `orchestration` calls this from the automatic post-operation check.

## Commands

```bash
# this module only
pytest src/measure -q

# one file
pytest src/measure/topology_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker is used anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

That is a real constraint on the performance tests, not a formality. `FakeEngine`
approximates every non-planar primitive by its bounding box (12 triangles), so
`create_primitive("ball", "sphere", …)` would make a density test pass while measuring
nothing. `intersections_test.py::_uv_sphere` builds Blender's own default 32x16 sphere as
explicit triangles through `engine.create_mesh` instead — real geometry, 960 triangles, the
same mesh the 6.5s figure was measured on. The real-Blender numbers quoted above were taken
out of band with `engine.create_engine()`; reproduce them that way rather than by adding a
marker here.

## Boundaries

- Write only inside `src/measure/**`. `src/contracts/`, `src/testing/`, and `conftest.py`
  are frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- If the contract in `src/contracts/` is missing something this module needs, do not edit
  it. File the need instead (see the main agent's contract-request process) and adapt
  locally against the current contract.
- `measure/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs
  in one of the four responsibility files instead.
- Nothing outside `measure/` may import `measure.metrics`, `measure.topology`, etc.
  directly — only `from measure import <name>`, per `measure/__init__.py`'s `__all__`.

## Implementation notes for whoever picks this up

- **`MeshSnapshot` already gives you `edges()` and `boundary_edges()`** in canonical order
  (`src/contracts/geometry.py`) — do not re-derive edge enumeration by hand in `topology.py`.
- **`AABB.overlaps(other, tol)`** is the broad-phase primitive `intersections.py` needs
  before any triangle-level test; do not skip straight to triangle-triangle intersection.
- **`Transform.has_unapplied_scale()`** already exists — `find_unapplied_transforms` is a
  thin wrapper over it, not a re-implementation.
- **`JoineryIntent.permits(overlap)`** already encodes the tolerance comparison — match a
  pair to an intent by `{object_id, into_object_id} == {a, b}`, then defer to `.permits()`
  rather than re-deriving the depth-plus-tolerance arithmetic.
- **`_broadphase.candidate_pairs` must stay a superset.** It returns every pair whose boxes
  could touch; two triangles that intersect necessarily have overlapping boxes, so the
  pruning changes the *work* and never the *answer*. Both its fallbacks (a mesh under
  `GRID_MIN_TRIANGLES`, a mesh whose triangles are all degenerate) fall back to *more* work.
  If a change would make a case unreliable, keep it exact and say so — a missed
  self-intersection is a `BLOCKER` the agent then exports.
- **Do not reach for `spatial.SpatialIndex` for intra-mesh triangle pruning.** It is keyed
  by object id and resolves every entry through `engine.world_bounds(object_id)`, so putting
  triangles in it means fabricating a fake engine — and its `pairs_overlapping` is a flat
  scan over every unordered pair, which measures 0.06s on 960 boxes and is 6s again at
  10 000. It is the right structure one level up, and `neighbours.py` uses it there.
- **A handler must never import `mcp_server`.** `mcp_server.registry` imports this module;
  the reverse closes a cycle and inverts `ARCHITECTURE.md`'s arrow. `_handlers.py` writes the
  one attribute it needs (`forge3d_context`) as a literal and degrades to `bind_engine` if
  that name ever changes.
- **`MeasurementReport` validates its own scope.** A handler that reaches a neighbour must
  put that neighbour in `scope` or construction raises — which is the point, and the reason
  `find_clipping`/`defect_report` widen `scope` from the pairs they actually examined.
- Keep the one-file-per-responsibility split from `README.md`. A defect finder that grows
  past the 300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module
  under `measure/`, not a bigger `topology.py`.

## Test layout

Mirrors the responsibility files exactly: `metrics_test.py`, `topology_test.py`,
`intersections_test.py`, `report_test.py`, `neighbours_test.py`, `registry_test.py`. A new
metric or defect class gets its test added to the matching file, not a new top-level test
file, unless it grows enough to need its own responsibility split (at which point split the
source file the same way first). `_broadphase.py` has no test file of its own: its contract
is observable through `find_self_intersections`, and
`intersections_test.py::test_self_intersection_examines_a_small_fraction_of_the_naive_triangle_pairs`
counts the calls that reach the exact test rather than reading inside the private module.
