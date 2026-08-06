"""``measure_angle``, ``make_parallel``, ``make_perpendicular``, ``set_angle``,
``make_plumb`` — the angle-parameterised family of immediate-snap alignments.

Grouped in one file because all five share one geometric primitive
(``_util.rotate_local_axis_onto``: rotate an object's chosen local axis onto a computed
world direction by the minimal delta) except ``make_plumb``, which reuses
``constraints.solve``/``transform_for`` directly instead — ``plumb`` is exactly
``ConstraintKind.PLUMB`` with no generalisation needed, so there is nothing to gain from
re-deriving it by hand (see the module's own docstring note below and ``align``'s
top-level ``README.md``, "why plumb and coplanar call into constraints.solve").

``measure_angle`` is the one pure query in this file: it never mutates and is what every
other function in this package uses to fill in ``AlignResult.angle_before_deg``/
``angle_after_deg``, so a caller can independently re-check what an align call reported.
"""

from __future__ import annotations

import math

from contracts import (
    Anchor,
    Constraint,
    ConstraintKind,
    ConstraintSet,
    EngineProtocol,
    Quat,
    Vec3,
)
from constraints import solve, transform_for
from measure import angle_between

from ._geom import perpendicular_in_plane, transforms_close
from ._util import require_object, rotate_local_axis_onto, up_angle_deg, world_axis
from .results import AlignResult

__all__ = ["measure_angle", "make_parallel", "make_perpendicular", "set_angle", "make_plumb"]

_AUTO_AXIS = "y"
"""``axis="auto"`` resolves to local +Y — the same "forward" convention
``constraints._orientation.dominant_axis`` fixes for ``parallel_to``/``perpendicular_to``,
and the axis every test fixture in this package (and in ``constraints/solver_kinds_test.py``
before it) elongates its beams along, so ``measure.angle_between``'s own dominant-*extent*
axis convention agrees with it for exactly the shapes this module's tests build."""


def measure_angle(engine: EngineProtocol, a: str, b: str) -> float:
    """Angle in degrees between two objects' dominant axes. Pure query — never mutates.

    Delegates entirely to ``measure.angle_between`` so this module can never silently
    disagree with the metric every other measurement tool in the product already reports
    (the same "one source of truth" reasoning ``constraints`` applies to its own re-use of
    ``resolve_anchor``).
    """
    require_object(engine, a, role="a")
    require_object(engine, b, role="b")
    return angle_between(engine, a, b).value


def _resolve_axis(axis: str) -> str:
    return _AUTO_AXIS if axis == "auto" else axis


def _apply_orientation(
    engine: EngineProtocol, object_id: str, to: str, axis: str, desired_world_dir: Vec3
) -> AlignResult:
    """Shared body for ``make_parallel``/``make_perpendicular``: compute the candidate
    transform, compare it to the object's current one, and either skip the engine call
    entirely (already aligned) or apply it. ``measure_angle`` before/after is what every
    caller's ``AlignResult`` reports, regardless of which local ``axis`` was actually
    rotated — the two-object dominant-axis reading is the metric this whole family is
    judged against."""
    before = measure_angle(engine, object_id, to)
    candidate = rotate_local_axis_onto(engine, object_id, axis, desired_world_dir)
    current = engine.snapshot(object_id).transform
    if transforms_close(candidate, current):
        return AlignResult(
            object_id=object_id, changed=False, angle_before_deg=before, angle_after_deg=before,
            detail=f"{object_id} is already aligned to {to} within tolerance",
        )
    engine.set_transform(object_id, candidate)
    after = measure_angle(engine, object_id, to)
    return AlignResult(
        object_id=object_id, changed=True, angle_before_deg=before, angle_after_deg=after,
        detail=f"rotated {object_id} to align with {to}",
    )


def make_parallel(engine: EngineProtocol, object_id: str, to: str, *, axis: str = "auto") -> AlignResult:
    """Rotate ``object_id`` by the minimal amount so its ``axis`` local axis (default: the
    object's forward axis, local +Y) points exactly along ``to``'s own same-named axis.

    Idempotent: a second call on an already-parallel pair reports ``changed=False`` and
    never touches the engine.
    """
    require_object(engine, object_id, role="object_id")
    require_object(engine, to, role="to")
    resolved_axis = _resolve_axis(axis)
    target_dir = world_axis(engine, to, resolved_axis)
    return _apply_orientation(engine, object_id, to, resolved_axis, target_dir)


def make_perpendicular(
    engine: EngineProtocol, object_id: str, to: str, *, axis: str = "auto"
) -> AlignResult:
    """Rotate ``object_id`` so its ``axis`` local axis lands at exactly 90 degrees from
    ``to``'s own same-named axis — never 0, never 180.

    The 90-degree direction is chosen deterministically (``_geom.perpendicular_in_plane``:
    a cross with world up), matching ``constraints``' own convention for
    ``perpendicular_to``.
    """
    require_object(engine, object_id, role="object_id")
    require_object(engine, to, role="to")
    resolved_axis = _resolve_axis(axis)
    target_dir = perpendicular_in_plane(world_axis(engine, to, resolved_axis))
    return _apply_orientation(engine, object_id, to, resolved_axis, target_dir)


def set_angle(
    engine: EngineProtocol, object_id: str, to: str, *, degrees: float
) -> AlignResult:
    """Rotate ``object_id``'s forward axis (local +Y) to exactly ``degrees`` from ``to``'s
    forward axis, measured about an axis perpendicular to ``to``'s own forward direction —
    so the result is exactly ``degrees`` regardless of how ``to`` itself is tilted.

    ``degrees=0`` is exactly ``make_parallel``'s result; ``degrees=90`` is exactly one of
    ``make_perpendicular``'s two valid results (the sign of the perpendicular is
    unconstrained by definition — see ``constraints._geom.perpendicular_in_plane``'s own
    docstring).
    """
    require_object(engine, object_id, role="object_id")
    require_object(engine, to, role="to")
    target_dir = world_axis(engine, to, "y")
    pivot = perpendicular_in_plane(target_dir)
    desired = Quat.from_axis_angle(pivot, math.radians(degrees)).rotate(target_dir).normalized()
    return _apply_orientation(engine, object_id, to, "y", desired)


def make_plumb(engine: EngineProtocol, object_id: str) -> AlignResult:
    """Rotate ``object_id`` so its local +Z equals world +Z, leaving its forward axis'
    in-plane heading otherwise as close to unchanged as that requirement allows.

    This is exactly ``ConstraintKind.PLUMB`` resolved once and applied immediately —
    reuses ``constraints.solve``/``transform_for`` rather than re-deriving the same
    up-preserving rotation construction by hand. The single most consequential alignment
    in the product (``contracts.geometry.WORLD_UP``'s own docstring): a railing post
    plumbed correctly on a sloped path is the flagship case ``constraints`` was built
    around, and ``align`` exists so an agent can apply that same correction to an object
    that was never given a standing constraint in the first place.
    """
    require_object(engine, object_id, role="object_id")
    before = up_angle_deg(engine, object_id)

    cs = ConstraintSet(
        object_id=object_id,
        constraints=(Constraint(kind=ConstraintKind.PLUMB, target=Anchor.world_up()),),
    )
    placement = solve(engine, cs)
    candidate = transform_for(placement)
    current = engine.snapshot(object_id).transform
    if transforms_close(candidate, current):
        return AlignResult(
            object_id=object_id, changed=False, angle_before_deg=before, angle_after_deg=before,
            detail=f"{object_id} is already plumb within tolerance",
        )
    engine.set_transform(object_id, candidate)
    after = up_angle_deg(engine, object_id)
    return AlignResult(
        object_id=object_id, changed=True, angle_before_deg=before, angle_after_deg=after,
        detail=f"rotated {object_id} plumb to world up",
    )
