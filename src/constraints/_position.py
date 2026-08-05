"""Position-affecting constraint kinds: what each one requires of an object's position.

Shared between ``solver.py`` (which applies a :class:`PositionEffect` to build a
``Placement``) and ``residual.py`` (which measures a stored ``Placement`` against the same
requirement) so the two functions can never silently disagree about what a constraint
demands — the same failure mode ``solve``/``dependency_order`` guard against for cycles.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import Constraint, ConstraintKind, EngineProtocol, Vec3

from ._geom import half_extent_along, replace_along_axis, support_along
from .anchors import resolve_anchor

__all__ = [
    "PositionEffect",
    "POSITION_KINDS",
    "position_effect",
    "apply_position_effect",
    "position_residual",
]

POSITION_KINDS = frozenset(
    {
        ConstraintKind.ON,
        ConstraintKind.FLUSH_WITH,
        ConstraintKind.CENTRED_ON,
        ConstraintKind.OFFSET_FROM,
        ConstraintKind.ENDS_AT,
        ConstraintKind.COPLANAR_WITH,
        ConstraintKind.SPACING,
        ConstraintKind.CLEAR_OF,
    }
)

_AXES = ("x", "y", "z")


@dataclass(frozen=True, slots=True)
class PositionEffect:
    """What one constraint requires of an object's position.

    Exactly one of ``axis``/``components``/``full`` is populated:

    - ``axis`` + ``scalar``: only the component along ``axis`` is constrained — the
      axis-parameterised family (``on``, ``flush_with``, ``offset_from``, ``spacing``,
      ``clear_of``, and the position half of ``coplanar_with``). ``axis`` is a direction,
      never a bitmask (``CLAUDE.md``).
    - ``components``: a named subset of x/y/z is constrained directly — ``centred_on``,
      the one kind whose ``axis`` is read component-wise instead.
    - ``full``: every component is replaced outright — ``ends_at``.

    ``one_sided`` marks ``clear_of``'s "at least" semantics: only a deficit below
    ``scalar`` counts against it, an overshoot never does.
    """

    axis: Vec3 | None = None
    scalar: float | None = None
    components: dict[str, float] | None = None
    full: Vec3 | None = None
    one_sided: bool = False


def _numeric_value(constraint: Constraint) -> float:
    v = constraint.value
    return v if isinstance(v, (int, float)) else 0.0


def _mover_half_extent(engine: EngineProtocol, object_id: str, axis: Vec3) -> float:
    """The moving object's own half-extent along ``axis``, from its *current* engine
    geometry. ``0.0`` when the object does not exist yet — a solve against an object not
    yet created in the engine (the hard/soft mechanics tests) still has to produce a
    placement, just without a self-size to offset by."""
    if not engine.exists(object_id):
        return 0.0
    return half_extent_along(engine.world_bounds(object_id), axis)


def position_effect(
    engine: EngineProtocol,
    object_id: str,
    constraint: Constraint,
    current_position: Vec3,
) -> PositionEffect:
    """The geometric requirement one position-affecting ``constraint`` places on
    ``object_id``, independent of hard/soft handling (that lives in ``solver.py``) and of
    whether it is being applied fresh or checked against an existing placement (that
    split lives in ``residual.py``)."""
    kind = constraint.kind
    resolution = resolve_anchor(engine, constraint.target)

    if kind == ConstraintKind.ON:
        axis = resolution.normal if resolution.normal is not None else Vec3(0.0, 0.0, 1.0)
        scalar = axis.normalized().dot(resolution.point) + _mover_half_extent(engine, object_id, axis)
        return PositionEffect(axis=axis, scalar=scalar)

    if kind == ConstraintKind.FLUSH_WITH:
        # Deliberately mirrors the *target's* own half-extent, never the mover's: the
        # mover need not exist yet for this to be checkable (see residual_test.py's
        # flush_with case, which measures a placement for an object never created).
        axis = constraint.axis if constraint.axis is not None else Vec3(1.0, 0.0, 0.0)
        bounds = engine.world_bounds(constraint.target.object_id)
        scalar = support_along(bounds, axis) + half_extent_along(bounds, axis)
        return PositionEffect(axis=axis, scalar=scalar)

    if kind == ConstraintKind.OFFSET_FROM:
        axis = constraint.axis if constraint.axis is not None else Vec3(1.0, 0.0, 0.0)
        scalar = axis.normalized().dot(resolution.point) + _numeric_value(constraint)
        return PositionEffect(axis=axis, scalar=scalar)

    if kind == ConstraintKind.SPACING:
        # Clear opening between neighbouring *surfaces*, not centre-to-centre pitch: the
        # target's own face plus the mover's own half-width plus the stated gap.
        axis = constraint.axis if constraint.axis is not None else Vec3(1.0, 0.0, 0.0)
        bounds = engine.world_bounds(constraint.target.object_id)
        scalar = (
            support_along(bounds, axis)
            + _numeric_value(constraint)
            + _mover_half_extent(engine, object_id, axis)
        )
        return PositionEffect(axis=axis, scalar=scalar)

    if kind == ConstraintKind.CLEAR_OF:
        axis = constraint.axis if constraint.axis is not None else Vec3(1.0, 0.0, 0.0)
        bounds = engine.world_bounds(constraint.target.object_id)
        minimum = (
            support_along(bounds, axis)
            + _numeric_value(constraint)
            + _mover_half_extent(engine, object_id, axis)
        )
        return PositionEffect(axis=axis, scalar=minimum, one_sided=True)

    if kind == ConstraintKind.COPLANAR_WITH:
        axis = resolution.normal if resolution.normal is not None else Vec3(0.0, 0.0, 1.0)
        scalar = axis.normalized().dot(resolution.point)
        return PositionEffect(axis=axis, scalar=scalar)

    if kind == ConstraintKind.CENTRED_ON:
        axis = constraint.axis if constraint.axis is not None else Vec3(1.0, 1.0, 1.0)
        components: dict[str, float] = {}
        for name in _AXES:
            if abs(getattr(axis, name)) > 1e-9:
                components[name] = getattr(resolution.point, name)
        return PositionEffect(components=components)

    if kind == ConstraintKind.ENDS_AT:
        return PositionEffect(full=resolution.point)

    raise ValueError(f"{kind!r} is not a position-affecting constraint kind")


def apply_position_effect(position: Vec3, effect: PositionEffect) -> Vec3:
    """``position`` updated to satisfy ``effect`` exactly (or, for ``one_sided``
    effects, left alone if it already clears the minimum)."""
    if effect.full is not None:
        return effect.full
    if effect.components is not None:
        return Vec3(
            effect.components.get("x", position.x),
            effect.components.get("y", position.y),
            effect.components.get("z", position.z),
        )
    if effect.axis is not None and effect.scalar is not None:
        if effect.one_sided:
            current = position.dot(effect.axis.normalized())
            if current >= effect.scalar - 1e-9:
                return position
        return replace_along_axis(position, effect.axis, effect.scalar)
    return position


def position_residual(position: Vec3, effect: PositionEffect) -> float:
    """How far ``position`` is from satisfying ``effect`` — always a non-negative
    magnitude (``Placement.residuals``' contract), never a signed direction."""
    if effect.full is not None:
        return (effect.full - position).length()
    if effect.components is not None:
        dx = effect.components.get("x", position.x) - position.x
        dy = effect.components.get("y", position.y) - position.y
        dz = effect.components.get("z", position.z) - position.z
        return Vec3(dx, dy, dz).length()
    if effect.axis is not None and effect.scalar is not None:
        actual = position.dot(effect.axis.normalized())
        if effect.one_sided:
            return max(0.0, effect.scalar - actual)
        return abs(effect.scalar - actual)
    return 0.0
