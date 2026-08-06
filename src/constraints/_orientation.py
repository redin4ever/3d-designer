"""Orientation-affecting constraint kinds: ``up`` and ``forward``.

Kept separate from ``_position.py`` because the two families combine independently — an
object can be ``flush_with`` a wall *and* ``plumb`` at the same time — and folding both
dispatches into one function would bury the up/forward precedence rules this file exists
to get right (``CLAUDE.md``'s PLUMB section, the reason the whole module exists per the
README's flagship example).
"""

from __future__ import annotations

from contracts import Constraint, ConstraintKind, EngineProtocol, Quat, Vec3, WORLD_UP

from ._geom import perpendicular_in_plane, require_direction, rotation_aligning
from .anchors import resolve_anchor
from .errors import UNSUPPORTED_KIND_RULE, ConstraintRuleError

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


def _unsupported(kind: ConstraintKind, family: str, kinds_name: str) -> ConstraintRuleError:
    """The dispatch guard's error. Reachable only from inside this package — ``solve``
    dispatches by set membership, so a kind arrives here exactly when it belongs to none of
    ``POSITION_KINDS``/``FORWARD_KINDS``/``UP_KINDS``.

    That makes this the first thing whoever adds the thirteenth ``ConstraintKind`` sees, so
    it names the set to add it to rather than restating the kind. As a bare ``ValueError``
    it said ``"<ConstraintKind.ON: 'on'> does not set forward"`` and left that reader to
    find the three sets themselves.
    """
    return ConstraintRuleError(
        rule=UNSUPPORTED_KIND_RULE,
        detail=f"{kind.value!r} is not a {family} constraint kind",
        suggestion=(
            f"if {kind.value!r} should set {family}, add it to "
            f"constraints._orientation.{kinds_name}; otherwise the caller dispatched to the "
            "wrong family"
        ),
    )


def forward_for(engine: EngineProtocol, constraint: Constraint) -> Vec3:
    """The world-space ``forward`` one of the forward-setting kinds requires.

    Raises :class:`ConstraintRuleError` for a kind outside :data:`FORWARD_KINDS` — see
    :func:`_unsupported` for who that message is written for.
    """
    kind = constraint.kind
    if kind == ConstraintKind.FOLLOWS:
        direction, _ = follows_rotation(engine, constraint)
        return direction
    if kind == ConstraintKind.PARALLEL_TO:
        return dominant_axis(engine, constraint.target.object_id)
    if kind == ConstraintKind.PERPENDICULAR_TO:
        return perpendicular_in_plane(dominant_axis(engine, constraint.target.object_id))
    raise _unsupported(kind, "forward-setting", "FORWARD_KINDS")


def up_for(engine: EngineProtocol, constraint: Constraint) -> Vec3:
    """The world-space ``up`` one of the up-setting kinds requires.

    Raises :class:`ConstraintRuleError` for a kind outside :data:`UP_KINDS`.
    """
    kind = constraint.kind
    if kind == ConstraintKind.PLUMB:
        resolution = resolve_anchor(engine, constraint.target)
        direction = resolution.direction if resolution.direction is not None else WORLD_UP
        return require_direction(
            direction, parameter="the plumb anchor's direction", context=constraint.target.key()
        )
    if kind == ConstraintKind.COPLANAR_WITH:
        resolution = resolve_anchor(engine, constraint.target)
        normal = resolution.normal if resolution.normal is not None else WORLD_UP
        return require_direction(
            normal, parameter="the coplanar target's face normal", context=constraint.target.key()
        )
    raise _unsupported(kind, "up-setting", "UP_KINDS")
