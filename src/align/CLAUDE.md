# align — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever picks this up next.

## Status

**GREEN.** `align_test.py`'s 24 tests were written first against the contract in
`src/contracts/` and the maths already proven out in `src/constraints/`/`src/measure/`
(Rule 4) — confirmed red on `NotImplementedError` (never `ImportError`/`AttributeError`)
before any function body existed, then implemented until green in the same pass. All 24
pass; the full `pytest src -q` suite passes alongside it.

## Commands

```bash
# this module only
pytest src/align -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker anywhere in this module — everything runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

## Boundaries

- Write only inside `src/align/**`. `src/contracts/`, `src/constraints/`, `src/measure/`,
  `src/testing/`, and `conftest.py` are frozen/owned-elsewhere surfaces (Rule 5) — read
  them, never edit them.
- If the contract in `src/contracts/` is missing something this module needs, do not edit
  it. This pass did not need to file anything — `constraints`/`measure`'s existing public
  surface (`solve`, `transform_for`, `resolve_anchor`, `angle_between`) covered every
  operation except `make_coplanar`'s numeric `face` index, which this module resolves
  itself (see `position.py::_nth_face`) rather than asking `contracts.Anchor` to grow a
  new field for one caller.
- `align/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs
  in one of the responsibility files instead.
- Nothing outside `align/` may import `align.orientation`, `align.position`, etc. directly
  — only `from align import <name>`, per `align/__init__.py`'s `__all__`.
- Do not import `bpy`. `EngineProtocol` is the only engine surface this module is written
  against.

## Implementation notes for whoever picks this up next

**`axis="auto"` is hard-coded to local +Y**, not a per-object "longest extent" computation.
This matches `constraints._orientation.dominant_axis`'s fixed convention exactly (not
`measure._geom.dominant_local_axis`'s extent-based one) so that `orientation.py`'s
minimal-delta-rotation helper (`_util.rotate_local_axis_onto`) and
`measure.angle_between`'s own extent-based metric agree — which they only do because every
test fixture in `align_test.py` (mirroring `constraints/solver_kinds_test.py`'s
`_rotated_beam` precedent) builds beams elongated along local Y. An object *not* built that
way will still get a geometrically correct "make forward parallel" result from
`make_parallel`/`make_perpendicular`/`set_angle` — it just will not necessarily be the
object's own longest axis, and `measure_angle`'s reading (which always uses the
extent-based metric via `measure.angle_between`) may disagree with which axis was actually
rotated. This is a real, documented seam between two conventions that predate this module
(`constraints` fixed Y before `measure` was built against extent) — not a bug to silently
paper over from within `align`'s write boundary.

**`make_plumb`, `make_coplanar` (default `face`), and `make_flush` call directly into
`constraints.solve`/`transform_for`.** `constraints.transform_for` always resets `scale` to
`(1, 1, 1)` (see its own source) — inherited here unchanged for `make_plumb` and
`make_coplanar`'s default-face path. `make_flush` deliberately does **not** inherit this:
since `flush_with` never touches rotation or scale, `position.py::make_flush` discards
`transform_for`'s reconstructed rotation/scale and copies the object's current ones
verbatim instead, so a non-default scale survives a flush untouched. A future pass wiring
scale-bearing objects through `make_plumb`/`make_coplanar` should decide deliberately
whether to special-case scale preservation there too, the same way `make_flush` already
does — this pass's test fixtures never exercise non-unit scale, so it was not forced.

**`snap_to_grid`'s rotation step only ever quantises yaw (rotation about world +Z)**, via
swing-twist decomposition (`_geom.z_swing_twist`), leaving any off-axis tilt as swing,
untouched. This is a deliberate scope choice, not a limitation discovered late: grid
snapping is inherently a plan-view (top-down) operation, and every test fixture in
`align_test.py` builds rotations purely about Z for exactly this reason. An object tilted
off any other axis will still have its bounds snapped correctly; only its yaw component of
rotation is quantised.

**`make_coplanar(face=i)` indexes into planar face groups sorted by rounded local normal**
(`position.py::_nth_face`, mirroring `constraints.anchors`' private `_face_groups` —
duplicated rather than imported, since it is private there per that package's own barrel
rule). The order is deterministic and stable across calls on the same mesh, but is not
guaranteed to match any particular "which face is 0" intuition (it is not, e.g., always the
+Z face) — a caller that cares which physical face a given index means should resolve it
once and reuse the index, not assume a fixed mapping.

**Cross-module note, not an `align` defect:** `src/mcp/_cap.py` documents that `ops` (4) +
`gaps` (8) + `align` (7) REFINE-role tools sum to 19, past the 8-tool accuracy-optimal
visible-set bound (ADR-003). `mcp.registry.cap_fairly` already handles this — round-robin
trimming with a logged warning, not a crash — and `mcp`'s own module docstring calls this
"a genuine cross-module coordination gap, not a defect in any one contributor," explicitly
naming `align` as one of the independently-correct contributors. Nothing in this module
should be changed to work around it; if the combined REFINE total needs to come down, that
is a `contracts.ToolRole` granularity question or an `ops`/`gaps`/`align` consolidation
question for the main agent to resolve across modules, not a reason to under-declare
`ALIGN_SPECS` here.

Keep the one-file-per-responsibility split from `README.md`. A function that grows past the
300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module under
`align/`, not a bigger `orientation.py`/`position.py`.

## Test layout

`align_test.py` covers the whole public surface in one file, organised by section comment
(`# --- make_parallel ---` etc.) rather than split per responsibility file — see
`README.md`'s Layout section for why. `_rotated_beam` is the one shared fixture helper,
deliberately mirroring `constraints/solver_kinds_test.py`'s function of the same name so a
37/50-degree starting angle means the same thing in both places. A new function's tests go
in the matching section; a new invariant (idempotence, error shape) gets its own test
rather than being folded into an existing one, so a future regression names exactly which
guarantee broke.

## Open contract requests

None filed. `constraints.solve`/`transform_for`/`resolve_anchor` and
`measure.angle_between` were sufficient to build every operation except `make_coplanar`'s
numeric `face` index, which this module resolves internally rather than asking
`contracts.Anchor` to grow numeric face selection for one caller (see the implementation
note above). If a second caller ever wants the same capability through `constraints`
itself, that is the point to file it — not before.
