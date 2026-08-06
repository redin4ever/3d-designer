"""Move, rotate, scale, delete, duplicate, rename, set material — the direct edits (Q-14).

Seven operations that did not exist. Every one of this library's other 33 kinds builds or
repairs something; none of them could nudge a part four centimetres to the left, so the
smallest correction an operator could want cost a whole round trip through the model.

**Why these are operations and not engine calls.** Q-19 chose one shared history for the
operator's edits and the agent's. Going through ``OPS`` means every manual edit is logged,
replayable, checkpointed and reachable by roll-back-N-steps, and it means the agent can do
these things too. A direct engine write would have produced a second timeline over one scene,
and two timelines that disagree describe nothing.

**Why validation is local rather than through ``validation.validate_params``.** That module's
per-kind dispatch is built around construction geometry — path arc length, shape tolerance,
degenerate polylines — and its ``acceptance_for`` counterpart answers phase-acceptance
queries about built structures. None of that applies to "put this object here". What does
apply is the convention behind it, which is kept: every parameter is checked on entry and
every failure is a ``ToolError`` naming a rule, the detail, and what to try instead.

**Snapping.** On by default, switchable (Q-16). Passing ``snap=0`` / ``snap_degrees=0`` turns
it off. A default that could not be turned off would be something to fight; no default at all
means every placement lands a fraction out, which is the defect class this product measures.
"""

from __future__ import annotations

import math
from typing import Any

from contracts import EngineProtocol, Operation, OperationResult, Quat, ToolError, Transform, Vec3

__all__ = [
    "move_object",
    "rotate_object",
    "scale_object",
    "delete_object",
    "duplicate_object",
    "rename_object",
    "set_object_material",
    "DEFAULT_SNAP_M",
    "DEFAULT_SNAP_DEGREES",
]

DEFAULT_SNAP_M = 0.1
"""Grid, in metres. Ten centimetres is fine enough for architectural placement and coarse
enough that dragging lands on it without aiming."""

DEFAULT_SNAP_DEGREES = 15.0
"""Angle snap. Divides 90 and 360 evenly, so the placements people actually want — square,
45, 30 — are all reachable exactly rather than approximately."""

_AXES = {"x": Vec3(1.0, 0.0, 0.0), "y": Vec3(0.0, 1.0, 0.0), "z": Vec3(0.0, 0.0, 1.0)}


def _require_object(engine: EngineProtocol, object_id: Any) -> str:
    """The object exists, named in the refusal if it does not.

    An operator can drag a part the agent deleted a moment ago — that is a normal way to find
    out it was deleted. Naming the id is the difference between "that is gone" and a stack
    trace. The scene is deliberately not listed: a refusal that inlines every object id is
    produced exactly when the caller is already lost (``scene_query``'s own rule).
    """
    if not isinstance(object_id, str) or not object_id:
        raise ToolError(
            rule="ops.invalid_parameter_value",
            detail=f"object_id must be a non-empty string, got {object_id!r}",
            suggestion="pass the id of the object to edit",
        )
    if not engine.exists(object_id):
        raise ToolError(
            rule="ops.unknown_object",
            detail=f"no object named {object_id!r}",
            suggestion="it may have been deleted since you selected it — reselect and try again",
        )
    return object_id


def _vec3(params: dict, name: str, *, required: bool = True, default: Vec3 | None = None) -> Vec3:
    raw = params.get(name)
    if raw is None:
        if required:
            raise ToolError(
                rule="ops.missing_parameter",
                detail=f"{name} is required",
                suggestion=f"pass {name} as [x, y, z] in metres",
            )
        return default if default is not None else Vec3()
    if isinstance(raw, Vec3):
        return raw
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise ToolError(
            rule="ops.invalid_parameter_value",
            detail=f"{name} must be [x, y, z], got {raw!r}",
            suggestion=f"pass {name} as three numbers in metres",
        )
    try:
        return Vec3(float(raw[0]), float(raw[1]), float(raw[2]))
    except (TypeError, ValueError) as exc:
        raise ToolError(
            rule="ops.invalid_parameter_value",
            detail=f"{name} components must be numbers: {exc}",
            suggestion=f"pass {name} as three numbers in metres",
        ) from exc


def _snapped(value: float, step: float) -> float:
    """Round to the nearest multiple of ``step``; ``step <= 0`` means no snapping.

    **Half steps round away from zero, not to even.** Python's built-in ``round`` is
    banker's rounding — ``round(2.5)`` is 2 — while JavaScript's ``Math.round`` rounds half
    up. The browser and this module both snap the same drag, and with the two conventions
    they disagreed on exactly the half-step cases: 0.25 snapped to a 0.1 grid gave 0.3 in the
    browser and 0.2 here. The operator would let go of a part, watch it sit where they put
    it, and see it jump one grid step on commit — intermittently, only on halves, which is
    the kind of thing that gets reported as "the snapping is broken sometimes" and never
    reproduced. ``ops/transform_test.py`` and ``frontend/tests/edit-tools.test.js`` pin the
    same cases on both sides so they cannot drift apart again.

    Re-rounded to nine places because ``round(1.03 / 0.1) * 0.1`` is 1.0000000000000002 in
    binary floating point, and a coordinate that prints as 1.0000000000000002 in a report
    reads as a precision bug in a product whose entire claim is verified numbers.
    """
    if step <= 0:
        return value
    steps = value / step
    away_from_zero = math.floor(abs(steps) + 0.5)
    return round(math.copysign(away_from_zero, steps) * step, 9)


def _snap_vec(v: Vec3, step: float) -> Vec3:
    return Vec3(_snapped(v.x, step), _snapped(v.y, step), _snapped(v.z, step))


def _float(params: dict, name: str, default: float) -> float:
    raw = params.get(name, default)
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ToolError(
            rule="ops.invalid_parameter_value",
            detail=f"{name} must be a number, got {raw!r}",
            suggestion=f"omit {name} for the default of {default}",
        ) from exc


def move_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Put one object at a world position.

    Required: ``object_id``, ``translation`` ``[x, y, z]``. Optional: ``snap`` (metres,
    default :data:`DEFAULT_SNAP_M`, ``0`` to disable).
    """
    object_id = _require_object(engine, op.params.get("object_id"))
    translation = _snap_vec(
        _vec3(op.params, "translation"), _float(op.params, "snap", DEFAULT_SNAP_M)
    )

    current = engine.snapshot(object_id).transform
    engine.set_transform(
        object_id, Transform(translation=translation, rotation=current.rotation, scale=current.scale)
    )
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=(object_id,))


def rotate_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Turn one object about a world axis.

    Required: ``object_id``, ``axis`` (``x``/``y``/``z``), ``degrees``. Optional:
    ``snap_degrees`` (default :data:`DEFAULT_SNAP_DEGREES`, ``0`` to disable).

    Axis-and-degrees rather than a quaternion because that is what a drag handle produces,
    and because snapping an angle is expressible in degrees and not in four components. The
    result is still composed as a quaternion — ``Quat``'s own docstring is the reason:
    compounding Euler edits across hundreds of operations accumulates gimbal-lock error.
    """
    object_id = _require_object(engine, op.params.get("object_id"))
    axis_name = str(op.params.get("axis", "")).lower()
    if axis_name not in _AXES:
        raise ToolError(
            rule="ops.invalid_parameter_value",
            detail=f"axis must be one of x, y, z — got {op.params.get('axis')!r}",
            suggestion="pass axis='z' to turn about the vertical",
        )

    degrees = _snapped(
        _float(op.params, "degrees", 0.0), _float(op.params, "snap_degrees", DEFAULT_SNAP_DEGREES)
    )
    turn = Quat.from_axis_angle(_AXES[axis_name], math.radians(degrees))

    current = engine.snapshot(object_id).transform
    engine.set_transform(
        object_id,
        Transform(translation=current.translation, rotation=turn, scale=current.scale),
    )
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=(object_id,))


def scale_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Resize one object. Required: ``object_id``, ``scale`` ``[x, y, z]``, all non-zero."""
    object_id = _require_object(engine, op.params.get("object_id"))
    scale = _vec3(op.params, "scale")
    if min(abs(scale.x), abs(scale.y), abs(scale.z)) == 0.0:
        # A zero component collapses the mesh into a plane, and every measurement taken from
        # it afterwards is meaningless. Refused on entry, like every other degenerate input
        # in this library (F-013, Gate B 5.4).
        raise ToolError(
            rule="ops.degenerate_geometry",
            detail=f"scale {(scale.x, scale.y, scale.z)} has a zero component",
            suggestion="every scale component must be non-zero — use a small value, not zero",
        )

    current = engine.snapshot(object_id).transform
    engine.set_transform(
        object_id,
        Transform(translation=current.translation, rotation=current.rotation, scale=scale),
    )
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=(object_id,))


def delete_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Remove one object.

    ``removed_objects`` is what tells the viewer to drop the node and the agent that the id
    is gone; a delete that reported nothing would leave a ghost in both.
    """
    object_id = _require_object(engine, op.params.get("object_id"))
    engine.delete(object_id)
    return OperationResult(op_id=op.op_id, ok=True, removed_objects=(object_id,))


def duplicate_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Copy one object.

    Required: ``object_id``, ``new_id``. Optional: ``offset`` ``[x, y, z]``, snapped like a
    move. Offsetting matters more than it looks: duplicating in place leaves two identical
    objects at the same coordinates, which is indistinguishable from nothing happening and is
    the first thing anyone tries.

    Returns whatever id the engine actually used — it uniquifies on collision rather than
    overwriting, and reporting the requested id would name an object that does not exist.
    """
    object_id = _require_object(engine, op.params.get("object_id"))
    new_id = op.params.get("new_id") or f"{object_id}_copy"
    offset = _snap_vec(
        _vec3(op.params, "offset", required=False), _float(op.params, "snap", DEFAULT_SNAP_M)
    )

    current = engine.snapshot(object_id).transform
    placed = Transform(
        translation=Vec3(
            current.translation.x + offset.x,
            current.translation.y + offset.y,
            current.translation.z + offset.z,
        ),
        rotation=current.rotation,
        scale=current.scale,
    )
    created = engine.duplicate(object_id, new_id, placed)
    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(created,))


def rename_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Give one object a different id.

    ``EngineProtocol`` has no rename, so this is duplicate-then-delete. That costs a full mesh
    copy, which is acceptable for an operator-driven action and would not be for a hot path.

    The taken-name check is not optional politeness: the engine auto-uniquifies on collision
    rather than erroring, so without it a rename onto an existing name silently produces a
    *third* name and the operator's part ends up called something neither of them chose.
    """
    object_id = _require_object(engine, op.params.get("object_id"))
    new_id = op.params.get("new_id")
    if not isinstance(new_id, str) or not new_id:
        raise ToolError(
            rule="ops.missing_parameter",
            detail="new_id is required",
            suggestion="pass the name you want the object to have",
        )
    if engine.exists(new_id):
        raise ToolError(
            rule="ops.name_taken",
            detail=f"{new_id!r} is already the name of another object",
            suggestion="pick a name nothing is using, or rename that object first",
        )

    current = engine.snapshot(object_id).transform
    created = engine.duplicate(object_id, new_id, current)
    engine.delete(object_id)
    return OperationResult(
        op_id=op.op_id, ok=True, produced_objects=(created,), removed_objects=(object_id,)
    )


def set_object_material(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Point one of an object's material slots at a material.

    Required: ``object_id``, ``material_id``. Optional: ``slot`` (default 0).
    """
    object_id = _require_object(engine, op.params.get("object_id"))
    material_id = op.params.get("material_id")
    if not isinstance(material_id, str) or not material_id:
        raise ToolError(
            rule="ops.missing_parameter",
            detail="material_id is required",
            suggestion="create a material first, then pass the id it returned",
        )

    slot = int(_float(op.params, "slot", 0.0))
    engine.assign_material(object_id, material_id, slot)
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=(object_id,))
