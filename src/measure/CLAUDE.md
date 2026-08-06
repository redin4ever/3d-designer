# measure — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Every function here is implemented and its suite passes. This module was built test-first (Rule 4): the tests were written against the contract, run, and confirmed failing on `NotImplementedError` before any body existed.

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
- Keep the one-file-per-responsibility split from `README.md`. A defect finder that grows
  past the 300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module
  under `measure/`, not a bigger `topology.py`.

## Test layout

Mirrors the four responsibility files exactly: `metrics_test.py`, `topology_test.py`,
`intersections_test.py`, `report_test.py`. A new metric or defect class gets its test added
to the matching file, not a new top-level test file, unless it grows enough to need its own
responsibility split (at which point split the source file the same way first).
