# align

One-shot geometric snaps — the IMMEDIATE-SNAP counterpart to `constraints`. `constraints`
expresses a *standing relationship* that re-solves when an anchor moves (ADR-002): constrain
a railing plumb to a stair, move the stair, the railing follows. `align` performs the
identical geometric correction *once, right now*, with no stored relationship left behind —
"make these two walls parallel" as a single correction an agent applies and moves on from,
not an ongoing rule it has to remember it created.

Stock Blender has no single built-in operator for "make parallel" / "make perpendicular" /
"make coplanar" between two arbitrary objects — this module is that gap, closed. Same maths
as `constraints` wherever a `ConstraintKind` already covers the operation exactly
(`make_plumb` is `ConstraintKind.PLUMB`, `make_flush` is `ConstraintKind.FLUSH_WITH`,
`make_coplanar`'s default face is `ConstraintKind.COPLANAR_WITH`), reusing
`constraints.solve`/`transform_for` directly rather than re-deriving them — different
lifecycle only.

## Public interface

Everything importable from `align` is declared in `align/__init__.py`. Nothing else is
public; do not import `align.orientation`, `align.position`, etc. directly from outside this
package.

```python
measure_angle(engine, a, b) -> float                              # degrees; never mutates

make_parallel(engine, object_id, to, *, axis="auto") -> AlignResult
make_perpendicular(engine, object_id, to, *, axis="auto") -> AlignResult
set_angle(engine, object_id, to, *, degrees) -> AlignResult        # 0 == make_parallel
make_plumb(engine, object_id) -> AlignResult                       # local +Z -> world +Z
make_coplanar(engine, object_id, to, *, face=None) -> AlignResult  # face: which planar face of `to`
make_flush(engine, object_id, to, *, axis) -> AlignResult          # axis is required, one of x/y/z
snap_to_grid(engine, object_id, *, grid, rotation_step_deg=0.0) -> AlignResult

ALIGN_SPECS: tuple[ToolSpec, ...]   # 7 MCP declarations, roles=(ToolRole.REFINE,), mutating=True

@dataclass(frozen=True)
class AlignResult:
    object_id: str
    changed: bool             # False means the engine was never touched — see Invariants
    angle_before_deg: float
    angle_after_deg: float
    detail: str
```

## Layout

One file per responsibility, so two agents extending different alignment behaviour never
touch the same file:

| File | Owns |
|---|---|
| `orientation.py` | `measure_angle`, `make_parallel`, `make_perpendicular`, `set_angle`, `make_plumb` |
| `position.py` | `make_coplanar`, `make_flush` |
| `grid.py` | `snap_to_grid` |
| `registry.py` | `ALIGN_SPECS` |
| `results.py` | `AlignResult` |
| `_geom.py` | Pure quaternion/vector math — no `EngineProtocol` in sight |
| `_util.py` | Engine-touching helpers built on `_geom.py` |

`align_test.py` covers the whole public surface in one file (not split per responsibility
like `constraints`' `solver_test.py`/`solver_kinds_test.py` pair): every function here is
small enough, and shares enough fixtures (`_rotated_beam`), that one file reads better than
seven thin ones.

## Invariants

- **Idempotent, by construction.** Every entry point computes a candidate transform first
  and compares it to the object's *current* one (`_geom.transforms_close`) before touching
  the engine at all. Within tolerance, it returns `changed=False` and calls
  `engine.set_transform` **zero times** — not once with an unchanged value. A second call on
  an already-aligned object is therefore not just numerically close to a no-op, it is one:
  the stored transform stays bit-for-bit what it was.
- **An align only ever moves what it names.** `make_flush(axis="x")` changes position on `x`
  alone; the other two position axes and all rotation come back exactly as they went in
  (verified by identity, not tolerance, where the source data allows it — see
  `position.py::make_flush`, which keeps the object's current rotation/scale objects
  verbatim rather than trusting a reconstruction to reproduce them).
- **Rotation is composed as quaternions throughout.** `_geom.rotation_aligning` (minimal
  rotation between two directions) and `_geom.z_swing_twist` (decompose/recompose about
  world +Z for `snap_to_grid`'s rotation step) are the only two rotation primitives in this
  package; Euler only appears at `snap_to_grid`'s `rotation_step_deg` parameter surface, per
  `contracts.Quat`'s own docstring on why (gimbal-lock error compounding across hundreds of
  agent operations).
- **`axis="auto"` means local +Y** — the same "forward" convention
  `constraints._orientation.dominant_axis` fixes for `parallel_to`/`perpendicular_to`. This
  agrees with `measure.angle_between`'s own dominant-*extent*-axis metric only for objects
  actually elongated along that axis (every test fixture in this package, and in
  `constraints/solver_kinds_test.py` before it, is built that way on purpose).
- **`set_angle(degrees=0)` is `make_parallel`; `degrees=90` is one of `make_perpendicular`'s
  two valid results.** All three share `orientation.py::_apply_orientation`; `set_angle`
  additionally rotates about an axis perpendicular to the target's own forward direction, so
  the resulting angle is exactly `degrees` regardless of how the target itself is tilted.
- **A missing object is a `contracts.ToolError`, never a bare `KeyError`.** Every public
  function validates every object id it takes, up front, via `_util.require_object` —
  before any other engine call — so the error shape never depends on which internal code
  path happened to touch the engine first (Gate A 4.2).
- **`make_coplanar`/`make_flush`/`make_plumb` call directly into
  `constraints.solve`/`transform_for`** rather than re-deriving plane-projection or
  face-support arithmetic by hand — the whole point of this package sharing its maths with
  `constraints`. `make_parallel`/`make_perpendicular`/`set_angle` do not: `contracts.Constraint`
  has no arbitrary-angle kind and no way to name an explicit local axis, so those three use
  this package's own `_util.rotate_local_axis_onto` instead, built from the same
  `_geom.rotation_aligning` formula `constraints._geom` uses (duplicated, not imported —
  that function is private to `constraints`, per its own barrel rule).
- **`make_coplanar`'s `face: int` has no `Anchor` representation to resolve through
  `constraints`** (only `AnchorKind.VERTEX`/`EDGE` read `Anchor.index`), so it is the one
  piece of new geometry in this package: `position.py::_nth_face` groups a snapshot's
  triangles into planar faces the same way `constraints.anchors`' private `_face_groups`
  does, then indexes into them in a deterministic (sorted-by-normal) order.

## Dependencies

`contracts`, `constraints` (`solve`, `transform_for`, `resolve_anchor` — all public), and
`measure` (`angle_between`, via `measure_angle`). No `bpy`, ever — everything is written
against `EngineProtocol`.

## Testing

`pytest src/align` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact
commands and implementation notes.
