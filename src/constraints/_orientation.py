"""Orientation-affecting constraint kinds: ``up`` and ``forward``.

Kept separate from ``_position.py`` because the two families combine independently — an
object can be ``flush_with`` a wall *and* ``plumb`` at the same time — and folding both
dispatches into one function would bury the up/forward precedence rules this file exists
to get right (``CLAUDE.md``'s PLUMB section, the reason the whole module exists per the
README's flagship example).
"""

from __future__ import annotations

from contracts import Constraint, ConstraintKind, EngineProtocol, Quat, Vec3, WORLD_UP

from ._geom import perpendicular_in_plane, rotation_aligning
from .anchors import resolve_anchor

__all__ = [
    "ORIENTATION_KINDS",
    "UP_KINDS",
    "FORWARD_KINDS",
    "dominant_axis",
    "follows_rotation",
    "forward_for",
    "up_for",
]

FORWARD_KINDS = frozenset(
    {ConstraintKind.FOLLOWS, ConstraintKind.PARALLEL_TO, ConstraintKind.PERPENDICULAR_TO}
)
UP_KINDS = frozenset({ConstraintKind.PLUMB, ConstraintKind.COPLANAR_WITH})
ORIENTATION_KINDS = FORWARD_KINDS | UP_KINDS


def dominant_axis(engine: EngineProtocol, object_id: str) -> Vec3:
    """A target's own local +Y in world space — what ``parallel_to``/``perpendicular_to``
    measure and align against. Never ``up`` (``CLAUDE.md``)."""
    snap = engine.snapshot(object_id)
    return snap.transform.rotation.rotate(Vec3(0.0, 1.0, 0.0)).normalized()


def follows_rotation(engine: EngineProtocol, constraint: Constraint) -> tuple[Vec3, Quat]:
    """``(forward, rotation)`` for a ``follows`` constraint.

    ``forward`` is the resolved path/edge tangent. ``rotation`` is the minimal rotation
    that produces it (local +Y onto the tangent) — reused by the solver to derive the
    *incidental* ``up`` a ``follows``-only object ends up with when nothing plumbs it, per
    the flagship negative test: aligning +Y to the tangent necessarily drags +Z along with
    it unless something overrides ``up`` afterwards.
    """
    resolution = resolve_anchor(engine, constraint.target)
    direction = resolution.direction if resolution.direction is not None else Vec3(0.0, 1.0, 0.0)
    if direction.length() < 1e-9:
        direction = Vec3(0.0, 1.0, 0.0)
    direction = direction.normalized()
    rotation = rotation_aligning(Vec3(0.0, 1.0, 0.0), direction)
    return direction, rotation


def forward_for(engine: EngineProtocol, constraint: Constraint) -> Vec3:
    """The world-space ``forward`` one of the forward-setting kinds requires."""
    kind = constraint.kind
    if kind == ConstraintKind.FOLLOWS:
        direction, _ = follows_rotation(engine, constraint)
        return direction
    if kind == ConstraintKind.PARALLEL_TO:
        return dominant_axis(engine, constraint.target.object_id)
    if kind == ConstraintKind.PERPENDICULAR_TO:
        return perpendicular_in_plane(dominant_axis(engine, constraint.target.object_id))
    raise ValueError(f"{kind!r} does not set forward")


def up_for(engine: EngineProtocol, constraint: Constraint) -> Vec3:
    """The world-space ``up`` one of the up-setting kinds requires."""
    kind = constraint.kind
    if kind == ConstraintKind.PLUMB:
        resolution = resolve_anchor(engine, constraint.target)
        direction = resolution.direction if resolution.direction is not None else WORLD_UP
        return direction.normalized()
    if kind == ConstraintKind.COPLANAR_WITH:
        resolution = resolve_anchor(engine, constraint.target)
        normal = resolution.normal if resolution.normal is not None else WORLD_UP
        return normal.normalized()
    raise ValueError(f"{kind!r} does not set up")
