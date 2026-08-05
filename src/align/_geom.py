"""Pure quaternion/vector math shared by every ``align`` entry point.

Nothing here touches ``EngineProtocol`` — every function is a plain function over
``contracts`` value types, which is what makes this file trivially unit-testable and safe
to reuse from ``orientation.py``, ``position.py`` and ``grid.py`` without any of them
importing the engine-touching helpers in ``_util.py``.

``rotation_aligning`` and ``perpendicular_in_plane`` mirror ``constraints._geom``'s
functions of the same name **exactly** (same formulas). They are not re-exported from
``constraints/__init__.py`` (private per that package's own barrel rule — see
``constraints/CLAUDE.md``: "Nothing outside constraints/ may import constraints.solver,
constraints.anchors, etc. directly"), so this module carries its own copy rather than
reaching past that boundary. Both are short, closed-form vector formulas with no solver
state — the kind of primitive unlikely to drift, unlike the multi-constraint orchestration
in ``constraints.solver`` that ``align`` calls directly instead of re-implementing (see
``position.py``).
"""

from __future__ import annotations

import math

from contracts import Quat, Transform, Vec3, WORLD_UP

__all__ = [
    "AXIS_NAMES",
    "axis_vector",
    "rotation_aligning",
    "perpendicular_in_plane",
    "z_swing_twist",
    "transforms_close",
]

AXIS_NAMES = ("x", "y", "z")

_AXIS_VECTORS = {
    "x": Vec3(1.0, 0.0, 0.0),
    "y": Vec3(0.0, 1.0, 0.0),
    "z": Vec3(0.0, 0.0, 1.0),
}


def axis_vector(axis: str) -> Vec3:
    """The unit local-space vector named by ``axis`` ("x", "y" or "z").

    Raises :class:`ValueError` on anything else — callers at the public surface convert
    that into a named :class:`~contracts.ToolError` (``_util.require_axis``); this stays a
    plain :class:`ValueError` because it is pure math with no engine context to attach a
    suggestion to.
    """
    try:
        return _AXIS_VECTORS[axis]
    except KeyError as exc:
        raise ValueError(f"{axis!r} is not a local axis name — use 'x', 'y' or 'z'") from exc


def rotation_aligning(from_axis: Vec3, to_direction: Vec3) -> Quat:
    """The minimal rotation taking ``from_axis`` onto ``to_direction``.

    Identical formula to ``constraints._geom.rotation_aligning`` — see the module
    docstring for why this is a deliberate, bounded duplication rather than an import.
    """
    f = from_axis.normalized()
    t = to_direction.normalized()
    dot = max(-1.0, min(1.0, f.dot(t)))
    axis = f.cross(t)
    if axis.length() < 1e-9:
        if dot > 0:
            return Quat.identity()
        perp = Vec3(1.0, 0.0, 0.0) if abs(f.x) < 0.9 else Vec3(0.0, 1.0, 0.0)
        flip_axis = f.cross(perp).normalized()
        return Quat.from_axis_angle(flip_axis, math.pi)
    return Quat.from_axis_angle(axis, math.acos(dot))


def perpendicular_in_plane(direction: Vec3) -> Vec3:
    """A vector perpendicular to ``direction``, chosen deterministically via a cross with
    world up (falling back to world +X when ``direction`` is itself vertical).

    Identical formula to ``constraints._geom.perpendicular_in_plane``. Any perpendicular
    vector satisfies "perpendicular", so this exists only to make the choice repeatable
    rather than depend on incidental floating-point order — the same rationale as the
    original.
    """
    d = direction.normalized()
    perp = d.cross(WORLD_UP)
    if perp.length() < 1e-6:
        perp = d.cross(Vec3(1.0, 0.0, 0.0))
    return perp.normalized()


def _quat_conjugate(q: Quat) -> Quat:
    return Quat(q.w, -q.x, -q.y, -q.z)


def z_swing_twist(rotation: Quat) -> tuple[Quat, float]:
    """Decompose ``rotation`` into ``(swing, twist_degrees)`` about world +Z.

    ``twist_degrees`` is the signed rotation about world +Z; ``swing`` is everything else
    (``rotation == swing * Quat.from_axis_angle(WORLD_UP, radians(twist_degrees))``, up to
    floating-point error). Used by :func:`align.snap_to_grid` to quantise only the yaw
    component of an object's rotation while leaving any off-axis tilt untouched — the
    standard swing-twist construction (project the quaternion's vector part onto the twist
    axis), not an Euler decomposition, so it stays exact under composition
    (``CONSTRAINTS`` in the module README: quaternions throughout, Euler only at a
    parameter surface).
    """
    proj = rotation.z  # component of the vector part along world +Z = (0,0,1)
    twist_raw = Quat(rotation.w, 0.0, 0.0, proj)
    twist_len = math.sqrt(twist_raw.w**2 + twist_raw.z**2)
    if twist_len < 1e-9:
        # Degenerate: a rotation exactly 180 degrees about an axis perpendicular to Z.
        # There is no meaningful yaw to extract; treat the whole rotation as swing.
        return rotation, 0.0
    twist = Quat(twist_raw.w / twist_len, 0.0, 0.0, twist_raw.z / twist_len)
    swing = (rotation * _quat_conjugate(twist)).normalized()
    twist_deg = math.degrees(2.0 * math.atan2(twist.z, twist.w))
    # Wrap into (-180, 180] so quantising near the wrap boundary is well-behaved.
    while twist_deg <= -180.0:
        twist_deg += 360.0
    while twist_deg > 180.0:
        twist_deg -= 360.0
    return swing, twist_deg


def transforms_close(
    a: Transform, b: Transform, *, pos_tol: float = 1e-6, angle_tol_deg: float = 1e-3
) -> bool:
    """Whether two transforms are the same, within tolerance.

    The single idempotence check every ``align`` entry point uses: a candidate transform
    that is already this close to the object's current one is treated as *no change*, so
    a second call on an already-aligned object reports ``changed=False`` and — because the
    caller skips ``engine.set_transform`` entirely in that case — leaves the stored
    transform bit-for-bit as it was, not merely numerically close to it.
    """
    if (a.translation - b.translation).length() > pos_tol:
        return False
    if (a.scale - b.scale).length() > pos_tol:
        return False
    dot = abs(
        a.rotation.w * b.rotation.w
        + a.rotation.x * b.rotation.x
        + a.rotation.y * b.rotation.y
        + a.rotation.z * b.rotation.z
    )
    angle_deg = math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))
    return angle_deg <= angle_tol_deg
