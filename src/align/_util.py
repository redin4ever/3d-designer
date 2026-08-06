"""Engine-touching helpers shared by every ``align`` entry point.

Split from ``_geom.py`` (Rule 2's "distinct actor" seam): everything here reads
``EngineProtocol`` state, where ``_geom.py`` is pure math over ``contracts`` value types
with no engine in sight. A function that needs both belongs here, thin, calling into
``_geom.py`` for the arithmetic.
"""

from __future__ import annotations

import math

from contracts import EngineProtocol, ToolError, Transform, Vec3, WORLD_UP

from ._geom import AXIS_NAMES, axis_vector, rotation_aligning

__all__ = [
    "require_object",
    "require_axis",
    "world_axis",
    "rotate_local_axis_onto",
    "up_angle_deg",
    "normal_angle_deg",
]


def require_object(engine: EngineProtocol, object_id: str, *, role: str) -> None:
    """Raise a named, suggestion-carrying error if ``object_id`` is not a live object.

    Every public ``align`` function that takes an object id calls this *before* touching
    the engine any further way, so a typo'd ``to=`` always surfaces the same error shape —
    :class:`~contracts.ToolError`, never a bare ``KeyError`` from deep inside
    ``engine.snapshot`` — regardless of which internal code path would otherwise have
    hit it first (Gate A 4.2).
    """
    if engine.exists(object_id):
        return
    known = ", ".join(sorted(engine.list_objects())) or "(none)"
    raise ToolError(
        "align.unknown_object",
        f"{role} {object_id!r} does not exist",
        f"known objects: {known}",
    )


def require_axis(axis: str) -> Vec3:
    """``_geom.axis_vector``, with a :class:`~contracts.ToolError` in place of the bare
    ``ValueError`` it raises — the public-surface error shape every other validation in
    this package uses."""
    try:
        return axis_vector(axis)
    except ValueError as exc:
        raise ToolError(
            "align.bad_axis", str(exc), f"use one of: {', '.join(AXIS_NAMES)}"
        ) from exc


def world_axis(engine: EngineProtocol, object_id: str, axis: str) -> Vec3:
    """World-space direction of ``object_id``'s local ``axis``, per its *current* engine
    transform."""
    rotation = engine.snapshot(object_id).transform.rotation
    return rotation.rotate(require_axis(axis)).normalized()


def rotate_local_axis_onto(
    engine: EngineProtocol, object_id: str, axis: str, desired_world_dir: Vec3
) -> Transform:
    """The transform that results from rotating ``object_id`` by the minimal amount that
    brings its local ``axis`` onto ``desired_world_dir``, leaving translation and scale
    untouched.

    This is the one geometric primitive behind ``make_parallel``, ``make_perpendicular``
    and ``set_angle``: each just computes a different ``desired_world_dir`` (the target's
    own axis; a perpendicular of it; a direction at an arbitrary angle from it) and calls
    through here. Composing the minimal delta rotation onto the object's *current*
    rotation — rather than rebuilding a rotation from scratch the way
    ``constraints.transform_for`` does from ``up``/``forward`` — is what keeps every axis
    other than the one named untouched beyond what the minimal rotation itself requires,
    matching this module's own "an align only ever moves what it names" invariant
    (README).
    """
    snap = engine.snapshot(object_id)
    current_dir = snap.transform.rotation.rotate(require_axis(axis)).normalized()
    delta = rotation_aligning(current_dir, desired_world_dir)
    new_rotation = (delta * snap.transform.rotation).normalized()
    return Transform(
        translation=snap.transform.translation, rotation=new_rotation, scale=snap.transform.scale
    )


def up_angle_deg(engine: EngineProtocol, object_id: str) -> float:
    """Angle in degrees between ``object_id``'s local +Z and world up. What
    ``make_plumb`` measures before/after — distinct from ``measure.angle_between``, which
    compares two *objects'* dominant axes rather than one object's up axis against the
    world."""
    up = engine.snapshot(object_id).transform.rotation.rotate(Vec3(0.0, 0.0, 1.0)).normalized()
    cosine = max(-1.0, min(1.0, up.dot(WORLD_UP)))
    return math.degrees(math.acos(cosine))


def normal_angle_deg(engine: EngineProtocol, object_id: str, plane_normal: Vec3) -> float:
    """Angle in degrees between ``object_id``'s local +Z (its own face-normal axis) and an
    arbitrary world-space ``plane_normal``. What ``make_coplanar`` measures before/after."""
    up = engine.snapshot(object_id).transform.rotation.rotate(Vec3(0.0, 0.0, 1.0)).normalized()
    n = plane_normal.normalized()
    cosine = max(-1.0, min(1.0, up.dot(n)))
    return math.degrees(math.acos(cosine))
