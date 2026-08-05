"""``snap_to_grid`` — quantise an object's world-space bounds (and, optionally, its yaw)
to regular multiples.

The one ``align`` operation with no ``to`` target: the "anchor" is a numeric spacing, not
another object's geometry, so this file has nothing to reuse from ``constraints`` and is
pure arithmetic over ``engine.world_bounds``/``engine.snapshot`` plus
``_geom.z_swing_twist``.
"""

from __future__ import annotations

import math

from contracts import EngineProtocol, Quat, ToolError, Transform, Vec3, WORLD_UP

from ._geom import transforms_close, z_swing_twist
from ._util import require_object
from .results import AlignResult

__all__ = ["snap_to_grid"]


def _snap_scalar(value: float, step: float) -> float:
    return round(value / step) * step


def snap_to_grid(
    engine: EngineProtocol, object_id: str, *, grid: float, rotation_step_deg: float = 0.0
) -> AlignResult:
    """Translate ``object_id`` so its world AABB minimum corner lands on a multiple of
    ``grid`` metres on every axis, and — when ``rotation_step_deg > 0`` — quantise its yaw
    (rotation about world +Z) to the nearest multiple of ``rotation_step_deg``, leaving any
    off-axis tilt untouched (``_geom.z_swing_twist``).

    ``rotation_step_deg=0`` (the default) never touches rotation at all, even if it is not
    itself a multiple of anything — only position is snapped.

    ``angle_before_deg``/``angle_after_deg`` report the object's own yaw (rotation about
    world +Z), the one thing ``rotation_step_deg`` actually quantises — not a two-object
    angle, since ``snap_to_grid`` has no ``to`` target.
    """
    require_object(engine, object_id, role="object_id")
    if grid <= 0:
        raise ToolError(
            "align.bad_grid", f"grid spacing {grid} must be positive", "pass a positive grid size in metres"
        )

    current = engine.snapshot(object_id).transform
    bounds_min = engine.world_bounds(object_id).minimum
    delta = Vec3(
        _snap_scalar(bounds_min.x, grid) - bounds_min.x,
        _snap_scalar(bounds_min.y, grid) - bounds_min.y,
        _snap_scalar(bounds_min.z, grid) - bounds_min.z,
    )
    new_translation = current.translation + delta

    _, twist_before = z_swing_twist(current.rotation)
    if rotation_step_deg > 0:
        swing, _ = z_swing_twist(current.rotation)
        twist_after = _snap_scalar(twist_before, rotation_step_deg)
        new_twist = Quat.from_axis_angle(WORLD_UP, math.radians(twist_after))
        new_rotation = (swing * new_twist).normalized()
    else:
        twist_after = twist_before
        new_rotation = current.rotation

    candidate = Transform(translation=new_translation, rotation=new_rotation, scale=current.scale)

    if transforms_close(candidate, current):
        return AlignResult(
            object_id=object_id, changed=False, angle_before_deg=twist_before, angle_after_deg=twist_before,
            detail=f"{object_id} is already grid-aligned within tolerance",
        )
    engine.set_transform(object_id, candidate)
    detail = f"snapped {object_id} to a {grid}m grid"
    if rotation_step_deg > 0:
        detail += f", rotation to {rotation_step_deg} degree steps"
    return AlignResult(
        object_id=object_id, changed=True, angle_before_deg=twist_before, angle_after_deg=twist_after,
        detail=detail,
    )
