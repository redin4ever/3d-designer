# detail — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Every function here is implemented and its suite passes. This module was built test-first (Rule 4): the tests were written against the contract, run, and confirmed failing on `NotImplementedError` before any body existed.

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

No `needs_blender` marker anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

## Boundaries

- Write only inside `src/detail/**`. `src/contracts/`, `src/testing/`, and `conftest.py` are
  frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- If the contract in `src/contracts/` is missing something this module needs (see the
  `MetricKind` gap noted in `README.md` and `report.py`), do not edit it. File the need and
  adapt locally against the current contract.
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
- Keep the one-file-per-responsibility split from `README.md`. A function that grows past the
  300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module under
  `detail/`, not a bigger source file.

## Test layout

Mirrors the five responsibility files, plus one for the shared result type:
`results_test.py`, `edges_test.py`, `apply_test.py`, `surface_test.py`, `materials_test.py`,
`report_test.py`. A new pass or parameter gets its test added to the matching file, not a new
top-level test file, unless it grows enough to need its own responsibility split (split the
source file the same way first).

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style visible in
`src/contracts/contracts_test.py` and `src/measure/`: dataclasses over dicts,
`from __future__ import annotations`, and a docstring on every test stating the product-level
consequence of the test failing — not just what it checks.
