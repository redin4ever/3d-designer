"""Shared geometry helpers for the constraint solver family.

Private to ``constraints`` — not re-exported from ``__init__.py`` (README's "one file per
responsibility" barrel rule). Split out because ``_position.py``, ``_orientation.py`` and
``solver.py`` all need the same small set of vector-support and minimal-rotation
primitives, and duplicating them per file is exactly the kind of drift the module split
exists to avoid.
"""

from __future__ import annotations

import math

from contracts import AABB, Quat, Vec3, WORLD_UP

__all__ = [
    "half_extent_along",
    "support_along",
    "replace_along_axis",
    "rotation_aligning",
    "perpendicular_in_plane",
]


def half_extent_along(bounds: AABB, axis: Vec3) -> float:
    """Half of ``bounds``'s extent projected onto ``axis`` (a support-function radius).

    Reduces to ``size.x / 2`` for ``axis = (1, 0, 0)`` and so on for the other basis
    directions, but stays correct for a non-axis-aligned direction too.
    """
    a = axis.normalized()
    size = bounds.size
    return 0.5 * (abs(a.x) * size.x + abs(a.y) * size.y + abs(a.z) * size.z)


def support_along(bounds: AABB, axis: Vec3) -> float:
    """``bounds``'s extreme scalar projection in the ``+axis`` direction — the position,
    along ``axis``, of the face of ``bounds`` that is furthest in that direction."""
    a = axis.normalized()
    return bounds.centre.dot(a) + half_extent_along(bounds, a)


def replace_along_axis(position: Vec3, axis: Vec3, required_scalar: float) -> Vec3:
    """``position`` with only its component along ``axis`` replaced by ``required_scalar``.

    Every direction orthogonal to ``axis`` is carried over unchanged — the module-wide "a
    constraint only ever moves what it names" invariant, specialised to a single axis
    direction (``offset_from``, ``flush_with``, ``spacing``, ``clear_of``, the position
    half of ``coplanar_with``, and ``on``'s vertical axis).
    """
    a = axis.normalized()
    current = position.dot(a)
    return position + a * (required_scalar - current)


def rotation_aligning(from_axis: Vec3, to_direction: Vec3) -> Quat:
    """The minimal rotation taking ``from_axis`` onto ``to_direction``.

    Generalises ``testing.mesh_helpers.rotation_from_up_to`` — which is exactly this
    function with ``from_axis == WORLD_UP`` — to an arbitrary source axis, so the same
    minimal-rotation pattern used there to lay an instance down onto a path can instead
    align an object's local +Y (``follows``) without a second, drifted implementation.
    """
    f = from_axis.normalized()
    t = to_direction.normalized()
    dot = max(-1.0, min(1.0, f.dot(t)))
    axis = f.cross(t)
    if axis.length() < 1e-9:
        if dot > 0:
            return Quat.identity()
        # Antiparallel: any axis perpendicular to f gives a valid 180-degree flip.
        perp = Vec3(1.0, 0.0, 0.0) if abs(f.x) < 0.9 else Vec3(0.0, 1.0, 0.0)
        flip_axis = f.cross(perp).normalized()
        return Quat.from_axis_angle(flip_axis, math.pi)
    return Quat.from_axis_angle(axis, math.acos(dot))


def perpendicular_in_plane(direction: Vec3) -> Vec3:
    """A vector perpendicular to ``direction``, chosen deterministically.

    Any perpendicular vector satisfies ``perpendicular_to`` (only the angle is
    constrained), so this picks one predictably — rotating within the horizontal plane
    via a cross with world up — rather than returning an arbitrary one that would make
    the result depend on incidental floating-point order.
    """
    d = direction.normalized()
    perp = d.cross(WORLD_UP)
    if perp.length() < 1e-6:
        perp = d.cross(Vec3(1.0, 0.0, 0.0))
    return perp.normalized()
