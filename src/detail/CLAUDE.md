# detail — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Every function here is implemented and its suite passes (80 tests, 10 of them
against real Blender). This module was built test-first (Rule 4): the tests were written
against the contract, run, and confirmed failing on `NotImplementedError` before any body
existed. The same applies to the F-008 (`DETAIL_SPECS`) and F-018 (bevel slivers) work — the
sliver ceiling was reproduced as a failing measurement against real Blender before a line of
the fix existed.

The tests in this directory were written against the module brief and `docs/decisions/gate-A.md`
waves 1.3 and 8.3/8.4 before any implementation existed (Rule 4) — they are the spec. Do not
change a test to make it pass; if a test seems wrong, re-read the docstring on the stub
function it targets first — the geometric conventions it depends on (dihedral angle formula,
convexity sign test, "hidden edge" definition) are derived and hand-verified in `edges.py`'s
and `edges_test.py`'s own docstrings, not invented ad hoc per test.

## Commands

```bash
# this module only
pytest src/detail -q

# one file
pytest src/detail/edges_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

```bash
# the one file that needs a real Blender
pytest src/detail/bevel_quality_test.py -q
```

**`bevel_quality_test.py` is the only `needs_blender` file here, and it must stay the only
one.** Everything else runs against `testing.FakeEngine` with no Blender installed. The
exception exists because `FakeEngine.bevel_edges` never moves a vertex — it duplicates a face
to model polygon growth — so a bevel-quality assertion written against the fake proves
nothing, and F-018 (bevel slivers) is a defect that only exists in real geometry. Everything
*decidable* about that fix lives in `topology.py`/`_polygon.py` and is tested without Blender;
only the "does a real bevel actually come out under the ceiling" claim needs bpy.

If you add a `needs_blender` test, mark it with `pytest.mark.needs_blender` (registered in
`pyproject.toml`; `conftest.py` skips it and reports the skip loudly when bpy is missing) and
take the engine from `engine.create_engine()`, never by constructing `BlenderEngine`.

## Boundaries

- Write only inside `src/detail/**`. `src/contracts/`, `src/testing/`, and `conftest.py` are
  frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- If the contract in `src/contracts/` is missing something this module needs, do not edit it.
  File the need and adapt locally against the current contract. (The `MetricKind` gap this
  file used to name is closed: `SHARP_EDGE_RATIO`, `TRIANGLE_ASPECT_RATIO` and
  `EDGE_LENGTH_UNIFORMITY` exist and `report.py`/`quality.py` use them directly.)
- `DETAIL_SPECS` names must match the handler names `src/app/handlers.py` registers under
  `"detail"`. A tool whose name does not match its handler is visible to an agent and
  executable by nothing — and it fails at call time, after the agent has committed to a plan.
  `cleanup_bevel_topology` is currently published here with no handler wired there yet; that
  entry belongs to the composition root, which is main-agent only.
- `detail/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs in
  one of the five responsibility files instead.
- Nothing outside `detail/` may import `detail.edges`, `detail.apply`, etc. directly — only
  `from detail import <name>`, per `detail/__init__.py`'s `__all__`.
- Do not depend on `src/measure/` — it is itself a throwing stub right now. `realism_report`
  computes triangle count fresh from `engine.snapshot()` rather than importing
  `measure.triangle_count`.

## Implementation notes for whoever picks this up

- **The dihedral/convexity/hidden formulas are already pinned down** in `edges.py`'s
  docstring and hand-verified against `unit_cube()` and the two hand-built strip fixtures in
  `edges_test.py` — do not re-derive a different sign convention. In particular: convex ⟺
  `dot(n1, other_vertex_of_t2 - shared_edge_point) < 0`, calibrated against a known-convex box
  edge; hidden ⟺ the average of the two adjacent face normals' Z component is negative.
- **`MeshSnapshot.edges()` and `.triangles` already give you everything needed** to find each
  edge's (up to two) adjacent triangles — build that adjacency map once per call, do not
  recompute it per edge.
- **`bevel_width_for` does not have a single mandated "characteristic size" formula.** Longest
  axis, bounding-box diagonal, and cube root of bounding volume are all defensible; the tests
  are written so any of them passes. Pick one, document the choice in `bevel_width_for`'s
  docstring when you implement it, and keep it consistent with `select_bevel_edges`'s own
  "exposed" notion (`WORLD_UP`).
- **`apply_edge_treatment` must let `EngineError` propagate.** Do not wrap
  `engine.bevel_edges`'s unapplied-scale error in a `try`/`except` that swallows or
  re-raises something else — the caller needs the real `EngineError` (see `apply_test.py`).
- **`vary_roughness` is called once per material/region, not once per scene.** "Uniform" is
  tested by calling it on several materials with `spread=0` and checking they all read back
  the same roughness; "varied" is tested the same way with `spread>0` and different seeds. Do
  not invent a multi-material-per-call naming scheme — the tests do not expect one.
- **`add_greebles` and `add_panel_lines` add geometry; they do not remove it.**
  `triangles_after >= triangles_before` always, and strictly greater whenever `changed` is
  `True`.
- **`Vec3.normalized()` raises below `EPSILON` (1e-4), which is bigger than real geometry.**
  A legitimate 2.4 mm x 3 mm bevel-corner triangle has a cross-product length around 7e-6.
  `edges.py::_triangle_normal` treats those as degenerate and skips them; `topology.py`
  cannot, because it has to triangulate the region they belong to — so it normalises by hand
  against a 1e-15 floor. Do not "simplify" either one into a `normalized()` call.
- **The cleanup's floor is the triangulation it was given.** `_polygon.best_triangulation`
  returns `None` unless a candidate strictly beats what was already there. On real bevel
  output the engine's own triangulation wins on roughly two thirds of regions, and a pass
  that "improved" those would make the mesh worse under the name of a quality step. This is
  also what makes `changed=False` honest and the pass idempotent under replay.
- **Three triangulation strategies, not one, and this is not over-engineering.** Measured on
  the F-018 tread: greedy ear clipping alone reaches 83.5, the dynamic program alone 90.8,
  the best-of-all-candidates 64.2 — they fail on different shapes. Deleting one costs real
  quality; check `bevel_quality_test.py` before you do.
- Keep the one-file-per-responsibility split from `README.md`. A function that grows past the
  300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module under
  `detail/`, not a bigger source file.

## Test layout

One test file per responsibility file: `results_test.py`, `edges_test.py`, `apply_test.py`,
`topology_test.py`, `cleanup_test.py`, `quality_test.py`, `surface_test.py`,
`materials_test.py`, `report_test.py`, `specs_test.py`, plus `bevel_quality_test.py` for the
real-Blender claims (see *Commands*). `_polygon.py` has no test file of its own on purpose —
it is private, and it is covered through `retriangulate_planar_regions` on hand-built shapes
(Rule 4: test the public interface; a private file that needs its own test wants to be a
module).

A new pass or parameter gets its test added to the matching file, not a new top-level test
file, unless it grows enough to need its own responsibility split (split the source file the
same way first).

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style visible in
`src/contracts/contracts_test.py` and `src/measure/`: dataclasses over dicts,
`from __future__ import annotations`, and a docstring on every test stating the product-level
consequence of the test failing — not just what it checks.
