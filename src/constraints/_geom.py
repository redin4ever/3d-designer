"""Shared geometry helpers for the constraint solver family.

Private to ``constraints`` — not re-exported from ``__init__.py`` (README's "one file per
responsibility" barrel rule). Split out because ``_position.py``, ``_orientation.py`` and
``solver.py`` all need the same small set of vector-support and minimal-rotation
primitives, and duplicating them per file is exactly the kind of drift the module split
exists to avoid.
"""

from __future__ import annotations

import math

from contracts import AABB, EPSILON, Quat, Vec3, WORLD_UP

from .errors import AXIS_RULE, ConstraintRuleError

__all__ = [
    "half_extent_along",
    "support_along",
    "replace_along_axis",
    "rotation_aligning",
    "perpendicular_in_plane",
    "require_direction",
]


def require_direction(vector: Vec3, *, parameter: str, context: str = "") -> Vec3:
    """``vector`` normalised, or a :class:`ConstraintRuleError` naming ``parameter``.

    The single place this package turns "a direction with no direction" into an error an
    agent can act on. Without it the failure is ``contracts.Vec3.normalized()``'s
    ``ValueError: cannot normalize a zero-length vector`` — which names no rule, no
    parameter, no constraint and no object, and points at a file in ``contracts`` that the
    agent has no reason to have read. Gate A 4.2 asks for the opposite of that, and the
    research reason it asks is that an agent handed an opaque error retries the identical
    call rather than changing anything.

    ``context`` is whatever identifies *which* input was wrong — the constraint kind, the
    object, the target anchor — and is what makes the difference between an error the agent
    can fix in one attempt and one it has to bisect a constraint set to locate.
    """
    if vector.length() < EPSILON:
        raise ConstraintRuleError(
            rule=AXIS_RULE,
            detail=(
                f"{parameter} is {vector.as_tuple()}, which has no direction"
                + (f" ({context})" if context else "")
            ),
            suggestion=(
                "give it a non-zero direction, e.g. Vec3(1, 0, 0). Note that `axis` is a "
                "direction for offset_from/flush_with/spacing/clear_of and a component-wise "
                "mask only for centred_on"
            ),
        )
    return vector.normalized()


def half_extent_along(bounds: AABB, axis: Vec3) -> float:
    """Half of ``bounds``'s extent projected onto ``axis`` (a support-function radius).

    Reduces to ``size.x / 2`` for ``axis = (1, 0, 0)`` and so on for the other basis
    directions, but stays correct for a non-axis-aligned direction too.
    """
    a = require_direction(axis, parameter="axis", context="measuring a bounding extent")
    size = bounds.size
    return 0.5 * (abs(a.x) * size.x + abs(a.y) * size.y + abs(a.z) * size.z)


def support_along(bounds: AABB, axis: Vec3) -> float:
    """``bounds``'s extreme scalar projection in the ``+axis`` direction — the position,
    along ``axis``, of the face of ``bounds`` that is furthest in that direction."""
    a = require_direction(axis, parameter="axis", context="measuring a bounding extent")
    return bounds.centre.dot(a) + half_extent_along(bounds, a)


def replace_along_axis(position: Vec3, axis: Vec3, required_scalar: float) -> Vec3:
    """``position`` with only its component along ``axis`` replaced by ``required_scalar``.

    Every direction orthogonal to ``axis`` is carried over unchanged — the module-wide "a
    constraint only ever moves what it names" invariant, specialised to a single axis
    direction (``offset_from``, ``flush_with``, ``spacing``, ``clear_of``, the position
    half of ``coplanar_with``, and ``on``'s vertical axis).
    """
    a = require_direction(axis, parameter="axis", context="placing a position along an axis")
    current = position.dot(a)
    return position + a * (required_scalar - current)


def rotation_aligning(from_axis: Vec3, to_direction: Vec3) -> Quat:
    """The minimal rotation taking ``from_axis`` onto ``to_direction``.

    Generalises ``testing.mesh_helpers.rotation_from_up_to`` — which is exactly this
    function with ``from_axis == WORLD_UP`` — to an arbitrary source axis, so the same
    minimal-rotation pattern used there to lay an instance down onto a path can instead
    align an object's local +Y (``follows``) without a second, drifted implementation.

    A zero-length argument raises :class:`ConstraintRuleError` naming *which* of the two it
    was. ``align._geom.rotation_aligning`` — the deliberate byte-for-byte duplicate of this
    function, see that module's docstring — guards identically and raises ``align``'s own
    named error instead; both are :class:`contracts.RuleError` s, and
    ``align/duplicated_geometry_test.py`` pins that they agree on everything else.
    """
    f = require_direction(from_axis, parameter="from_axis", context="rotation_aligning")
    t = require_direction(to_direction, parameter="to_direction", context="rotation_aligning")
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

    A zero-length ``direction`` raises :class:`ConstraintRuleError`: there is no plane to be
    perpendicular *in*, so any answer would be a guess presented as a measurement.
    """
    d = require_direction(direction, parameter="direction", context="perpendicular_in_plane")
    perp = d.cross(WORLD_UP)
    if perp.length() < 1e-6:
        perp = d.cross(Vec3(1.0, 0.0, 0.0))
    return perp.normalized()
