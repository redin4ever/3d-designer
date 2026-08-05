# constraints

The solver behind the product's headline number. A model producing raw x/y/z coordinates
lands within 2x of ground truth about 37% of the time — even one purpose-trained for
spatial estimation. A model emitting the twelve declarative constraint types in
`contracts.ConstraintKind` and letting this module resolve them measures 91-95% (ADR-004).
This module *is* that solver.

Constraints are **stored, not just applied** (ADR-002): `solve`/`solve_all` are meant to
be re-run whenever upstream geometry changes, and `satisfies` is what lets a caller tell
"still valid" from "needs a re-solve" without paying for a fresh solve every time — move
the stair, and the railing constrained to its outer edge follows.

## Public interface

Everything importable from `constraints` is declared in `constraints/__init__.py`. Nothing
else is public; do not import `constraints.solver`, `constraints.anchors`, etc. directly
from outside this package.

```python
solve(engine, cs, *, others=()) -> Placement
    # resolve one object's constraints against current geometry

solve_all(engine, sets) -> tuple[Placement, ...]
    # topologically ordered; raises ConstraintError(rule=CYCLE_RULE) on a cycle

dependency_order(sets) -> tuple[str, ...]
    # raises ConstraintError(rule=CYCLE_RULE) if the graph has a cycle

resolve_anchor(engine, anchor) -> AnchorResolution
    # AnchorResolution: frozen dataclass — .point, .normal, .direction, .path

satisfies(engine, cs, placement) -> tuple[tuple[str, float], ...]
    # residual per constraint; empty means every constraint met exactly.
    # re-checkable after an upstream anchor moves, without re-solving.

transform_for(placement) -> Transform
    # the engine Transform that realises a solved Placement
```

## Layout

One file per responsibility, so two agents extending different constraint behaviour never
touch the same file:

| File | Owns |
|---|---|
| `anchors.py` | `AnchorResolution` (real dataclass) + `resolve_anchor` |
| `solver.py` | `solve`, `solve_all`, `transform_for` |
| `graph.py` | `dependency_order` and cycle detection |
| `residual.py` | `satisfies` |

Test files mirror this **except `solver.py`**, which is tested from two angles rather than
one file: `solver_test.py` covers solving *mechanics* (escape hatch, hard/soft, re-solve,
batching, errors) and `solver_kinds_test.py` covers the *geometry* each of the twelve
`ConstraintKind` values produces, one test per kind. A single 600+-line file covering both
concerns would bury a change to one behind noise from the other; see `CLAUDE.md` for the
full rationale.

## Invariants

- **The escape hatch bypasses solving entirely.** `cs.uses_escape_hatch` solves to exactly
  `cs.raw_position` — it is not "one constraint among many" blended in with the rest
  (ADR-004). This is what keeps its use visible in the operation log rather than silent.
- **A constraint only ever moves what it names.** Any position axis or orientation
  component no constraint touches is carried over unchanged from the object's current
  engine transform. `centred_on` naming only `x, y` must leave `z` exactly where it was.
- **Hard fails loud, soft reports and moves on.** A HARD constraint (the default —
  `Constraint.hard`) that cannot be met raises `ConstraintError`. A SOFT one is satisfied
  best-effort; its shortfall lands in `Placement.residuals` and
  `Placement.satisfied_all_hard` stays `True` as long as every HARD constraint held.
- **A missing object is a `ConstraintError`, never a bare `KeyError`.** Every error names
  the missing id and carries a `suggestion` (Gate A 4.2) — an agent handed a raw traceback
  loops on the same broken call.
- **`up` and `forward` are the object's own local +Z and +Y axes, in world space.** A
  constraint that does not touch orientation leaves both exactly as the object's current
  transform already has them. `plumb` sets `up` to world vertical; `follows` sets `forward`
  to the path tangent; `parallel_to`/`perpendicular_to`/`coplanar_with` measure or set
  whichever of the two the constraint is actually about. This convention is not yet in
  `contracts.Placement`'s docstrings (filed as a contract request) — it lives here until it
  does.
- **PLUMB overrides only `up`.** It never touches `forward`, and it is *not* the same as
  the path normal — posts normal to a stair rake is the single most common
  naive-generator error the product exists to prevent (`ConstraintKind.PLUMB` docstring).
- **`dependency_order`/`solve_all` fail loudly on a cycle, never partially.** A diamond
  (two nodes sharing one target) is not a cycle and must solve.
- **No dependency on `src/measure/`.** It is a stub itself; any measurement this module
  needs is computed directly from `engine.snapshot`/`engine.world_bounds`.

## Dependencies

`contracts` only. No import of `measure`, `spatial`, or `bpy`.

## Testing

`pytest src/constraints` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact
commands and the local test-file layout.
