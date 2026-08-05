# constraints — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever writes the bodies of the stubs here.

## Status

Currently **RED by design**. Every function in `anchors.py`, `solver.py`, `graph.py` and
`residual.py` raises `NotImplementedError("constraints.<name>: not implemented")`.
`AnchorResolution` in `anchors.py` is the one exception — a real, fully-implemented frozen
dataclass, not a stub. The 37 tests in this directory were written against the contract in
`src/contracts/` and the docstrings on `contracts.ConstraintKind` before any implementation
existed (Rule 4) — they are the spec. Do not change a test to make it pass; if a test seems
wrong, it is describing a real product requirement (re-read
`docs/adr/ADR-004-typed-operations-constraint-placement.md` before concluding otherwise).

## Commands

```bash
# this module only
pytest src/constraints -q

# one file
pytest src/constraints/solver_kinds_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker is used anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

## Boundaries

- Write only inside `src/constraints/**`. `src/contracts/`, `src/testing/`, and
  `conftest.py` are frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- If the contract in `src/contracts/` is missing something this module needs, do not edit
  it. File the need instead (see the main agent's contract-request process) and adapt
  locally against the current contract.
- `constraints/__init__.py` is a barrel: re-exports only. If it grows logic, that logic
  belongs in one of the four responsibility files instead.
- Nothing outside `constraints/` may import `constraints.solver`, `constraints.anchors`,
  etc. directly — only `from constraints import <name>`, per `constraints/__init__.py`'s
  `__all__`.
- Do not import `measure`. It is a stub itself (`src/measure/`); anything this module needs
  to know about geometry is computed directly from `engine.snapshot`/`engine.world_bounds`.

## Implementation notes for whoever picks this up

**The `up`/`forward` convention (not yet formalised in `contracts.Placement`, see the
contract request below) is the load-bearing design decision the whole test suite assumes:**

- `up` is the world-space direction of the object's own local +Z axis. `forward` is the
  world-space direction of its local +Y axis. Both default to whatever the object's
  *current* engine transform already encodes when no constraint touches them —
  `solver_test.py::test_resolving_again_after_the_anchor_moves_moves_the_dependent_with_it`
  and the `centred_on` test in `solver_kinds_test.py` both depend on this "untouched axes
  are carried over, not reset" behaviour.
- `plumb` sets `up = world up` and leaves `forward` alone.
- `follows` sets `forward` to the resolved path/edge tangent. Without `plumb` present,
  `up` is free to tilt away from vertical (the naive, undesired case the flagship
  `solver_kinds_test.py::test_plumb_holds_up_vertical_on_a_31_degree_rake` /
  `test_without_plumb_following_the_same_rake_may_tilt_up_off_vertical` pair exists to
  tell apart) — see `testing/mesh_helpers.py::rotation_from_up_to` for the existing
  precedent this mirrors.
- `parallel_to`/`perpendicular_to` measure and set `forward` against the target's own
  dominant axis (its local +Y in world space), never `up`.
- `coplanar_with` sets `up` to the target plane's normal and moves `position` onto the
  plane, so every one of the object's own local points ends up in the plane once
  `transform_for` is applied — not just the object's origin.

**Axis-parameterised constraints (`offset_from`, `flush_with`, `spacing`, `clear_of`) all
read `Constraint.axis` the same way: a direction vector, not a bitmask.** `centred_on` is
the one exception — its `axis` is read component-wise as "align this axis" (a nonzero
component means aligned, per `solver_kinds_test.py::test_centred_on_...`), because it names
a *set* of axes rather than a single direction.

**`Anchor.index` selects into `MeshSnapshot.edges()`'s existing canonical ordering**
(`src/contracts/geometry.py`) for `AnchorKind.EDGE` — do not invent a second edge
enumeration. The same field selects a vertex index for `AnchorKind.VERTEX`.

**A 2-vertex, 0-face mesh (`engine.create_mesh(id, [p0, p1], [])`) is how the test suite
represents a bare path/edge target** for `AnchorKind.PATH` (see `solver_kinds_test.py`'s
`stair_rake`/`fence_line` fixtures) — `MeshSnapshot` only requires at least one vertex, not
any faces, so this is valid input, not a workaround.

**`AnchorKind.FACE`'s `feature` string is free-form by contract** (`Anchor.feature: str`)
— the test suite uses `"top"` for a box's upper face and `"face"` for a plane primitive's
single face. Do not read anything into the literal strings beyond "whichever face the
caller means"; there is no enum backing them.

Keep the one-file-per-responsibility split from `README.md`. A constraint kind's solving
logic that grows past the 300-line soft cap (`.claude/rules/modularity.md`) wants a private
helper module under `constraints/`, not a bigger `solver.py`.

## Test layout

Mirrors the four responsibility files **except `solver.py`, which is tested from two
files**: `solver_test.py` (mechanics — escape hatch, hard/soft, re-solve, batching, error
shape) and `solver_kinds_test.py` (one test per `ConstraintKind`, plus the PLUMB flagship's
negative case). `solve` is a single function serving all twelve constraint kinds, so it
cannot be split the way `measure`'s multi-function files can — see
`measure/CLAUDE.md`'s own "split the source file the same way first" caveat, which does not
apply here because there is only one function to split *tests* around, not source. A new
constraint kind's geometric test goes in `solver_kinds_test.py`; a new solving-mechanics
test goes in `solver_test.py`. Anchor-resolution tests go in `anchors_test.py`, ordering and
cycle tests in `graph_test.py`, residual tests in `residual_test.py`.

## Open contract request

`contracts.Placement.up` and `.forward` currently carry no docstring explaining what they
mean — this module had to establish that convention itself (see above) to have anything
concrete to test against. Filed as a contract request rather than edited directly (Rule 5):
`contracts.Placement` should document `up`/`forward` as "world-space direction of the
object's own local +Z / +Y axis" so every future consumer of a `Placement` — not just this
solver — agrees on what the two fields mean.
