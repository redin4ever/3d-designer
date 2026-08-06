"""The constraint solver — turns a declarative constraint set into a concrete placement.

This is the module the product's headline number is about: raw x/y/z placement lands
within 2x of ground truth roughly 37% of the time even from a model purpose-trained for
spatial estimation; constraints resolved by a solver measure 91-95% (ADR-004). Every other
file in this package exists to support what happens here.

Split into private helpers (``_position.py``, ``_orientation.py``, ``_geom.py``) per
``CLAUDE.md``'s modularity note: ``solve`` is one function serving all twelve constraint
kinds and cannot be split the way a multi-function file can, but the per-family geometry it
depends on can live elsewhere so this file stays about *orchestration* — carry-over,
hard/soft, escape hatch, batching — not about what each kind computes.
"""

from __future__ import annotations

import math
from typing import Sequence

from contracts import (
    Constraint,
    ConstraintKind,
    ConstraintSet,
    EngineProtocol,
    Placement,
    Quat,
    Transform,
    Vec3,
    WORLD_UP,
)

from ._geom import rotation_aligning
from .errors import ConstraintRuleError
from ._orientation import follows_rotation, forward_for, up_for
from ._position import POSITION_KINDS, apply_position_effect, position_effect, position_residual
from .graph import dependency_order

__all__ = ["solve", "solve_all", "transform_for"]

_CONTRADICTION_RULE = "constraints.contradictory_hard"


def _current_state(engine: EngineProtocol, object_id: str) -> tuple[Vec3, Vec3, Vec3]:
    """``(position, up, forward)`` an object already has, before any constraint touches
    it. Falls back to the identity transform's basis when the object does not exist yet
    in the engine — a solve against a not-yet-created object (the hard/soft mechanics
    tests) still needs *something* to carry unnamed axes over from."""
    if engine.exists(object_id):
        t = engine.snapshot(object_id).transform
        up = t.rotation.rotate(Vec3(0.0, 0.0, 1.0))
        forward = t.rotation.rotate(Vec3(0.0, 1.0, 0.0))
        return t.translation, up, forward
    return Vec3(0.0, 0.0, 0.0), WORLD_UP, Vec3(0.0, 1.0, 0.0)


def _axis_key(axis: Vec3) -> tuple[float, float, float]:
    a = axis.normalized()
    return (round(a.x, 6), round(a.y, 6), round(a.z, 6))


def _solve_position(
    engine: EngineProtocol,
    object_id: str,
    constraints: Sequence[Constraint],
    current_position: Vec3,
) -> tuple[Vec3, tuple[tuple[str, float], ...]]:
    position = current_position
    axis_claims: dict[tuple[float, float, float], float] = {}
    residuals: list[tuple[str, float]] = []
    position_constraints = [c for c in constraints if c.kind in POSITION_KINDS]

    # Pass 1: every HARD constraint applies. A later hard constraint that disagrees with
    # an earlier one on the same axis is a genuine contradiction — no position satisfies
    # both, so this raises rather than silently picking a side (Constraint.hard docstring).
    for c in position_constraints:
        if not c.hard:
            continue
        effect = position_effect(engine, object_id, c, position)
        if effect.axis is not None and effect.scalar is not None:
            key = _axis_key(effect.axis)
            claimed = axis_claims.get(key)
            if claimed is not None and abs(claimed - effect.scalar) > c.tolerance:
                raise ConstraintRuleError(
                    rule=_CONTRADICTION_RULE,
                    detail=(
                        f"{object_id!r}: two hard constraints require different positions "
                        f"along axis {effect.axis.as_tuple()} "
                        f"({claimed:.4f}m vs {effect.scalar:.4f}m)"
                    ),
                    suggestion="make one of the conflicting constraints soft, or remove one",
                )
            axis_claims[key] = effect.scalar
        position = apply_position_effect(position, effect)

    # Pass 2: SOFT constraints. One that does not conflict with anything hard is applied
    # too (best-effort — nothing stops it succeeding); one that does conflict is left
    # alone and reports its shortfall instead, never escalated into a failure.
    for c in position_constraints:
        if c.hard:
            continue
        effect = position_effect(engine, object_id, c, position)
        if effect.axis is not None and effect.scalar is not None:
            key = _axis_key(effect.axis)
            if key not in axis_claims:
                axis_claims[key] = effect.scalar
                position = apply_position_effect(position, effect)
                continue
        diff = position_residual(position, effect)
        if diff > c.tolerance:
            residuals.append((f"{c.kind.value} -> {c.target.key()}", diff))

    return position, tuple(residuals)


def _solve_orientation(
    engine: EngineProtocol,
    constraints: Sequence[Constraint],
    current_up: Vec3,
    current_forward: Vec3,
) -> tuple[Vec3, Vec3]:
    up = current_up
    forward = current_forward
    tilt_rotation: Quat | None = None
    overrides_up = any(
        c.kind in (ConstraintKind.PLUMB, ConstraintKind.COPLANAR_WITH) for c in constraints
    )

    for c in constraints:
        if c.kind == ConstraintKind.FOLLOWS:
            direction, rotation = follows_rotation(engine, c)
            forward = direction
            tilt_rotation = rotation
        elif c.kind in (ConstraintKind.PARALLEL_TO, ConstraintKind.PERPENDICULAR_TO):
            forward = forward_for(engine, c)
        elif c.kind in (ConstraintKind.PLUMB, ConstraintKind.COPLANAR_WITH):
            up = up_for(engine, c)

    # PLUMB overrides only `up`, never `forward` (CLAUDE.md). Without it (or coplanar_with)
    # present, `follows` alone is free to tilt `up` away from vertical — the naive case the
    # flagship pair of tests exists to tell apart from the plumb one.
    if tilt_rotation is not None and not overrides_up:
        up = tilt_rotation.rotate(Vec3(0.0, 0.0, 1.0))

    return up, forward


def solve(
    engine: EngineProtocol, cs: ConstraintSet, *, others: Sequence[str] = ()
) -> Placement:
    """Resolve one object's constraints against the engine's current geometry.

    ``cs.uses_escape_hatch`` solves to exactly ``cs.raw_position`` (ADR-004) — the raw
    coordinate path is deliberately not "one constraint among many"; it bypasses solving
    entirely so its use stays visible in the operation log rather than silently blended
    in with everything else.

    Any axis or orientation component no constraint names is carried over from the
    object's current engine transform, unchanged — a constraint only ever moves what it
    says it moves.

    A HARD constraint (the default — see :attr:`contracts.Constraint.hard`) that cannot be
    met raises :class:`~constraints.ConstraintRuleError`. A SOFT constraint that cannot be met is
    satisfied on a best-effort basis; its shortfall is reported in
    :attr:`contracts.Placement.residuals` and
    :attr:`~contracts.Placement.satisfied_all_hard` stays ``True`` as long as every HARD
    constraint was actually met.

    A constraint naming an object that does not exist raises
    :class:`~constraints.ConstraintRuleError` — never a bare ``KeyError`` — carrying the missing
    id and a ``suggestion`` (Gate A 4.2).

    ``others`` names sibling objects already placed earlier in this ``solve_all`` batch,
    for constraints (``spacing``, ``clear_of``) that need a neighbour's *solved* placement
    rather than its resting engine transform. ``solve_all`` keeps this current by writing
    each solved placement back to the engine before solving the next object, so those
    constraints read live geometry without this function needing its own placement cache.
    """
    del others  # solve_all keeps the engine itself current; see docstring above.

    current_position, current_up, current_forward = _current_state(engine, cs.object_id)

    if cs.uses_escape_hatch:
        return Placement(
            object_id=cs.object_id,
            position=cs.raw_position,
            up=current_up,
            forward=current_forward,
        )

    position, residuals = _solve_position(engine, cs.object_id, cs.constraints, current_position)
    up, forward = _solve_orientation(engine, cs.constraints, current_up, current_forward)

    return Placement(
        object_id=cs.object_id,
        position=position,
        up=up,
        forward=forward,
        residuals=residuals,
        satisfied_all_hard=True,
    )


def solve_all(engine: EngineProtocol, sets: Sequence[ConstraintSet]) -> tuple[Placement, ...]:
    """Solve every set in dependency order, each target resolved before its dependent.

    Raises :class:`~constraints.ConstraintRuleError` with ``rule == CYCLE_RULE`` on a cyclic
    graph, via :func:`constraints.dependency_order` — the same failure, not a re-derived
    one, so a caller only ever handles one cycle-detection code path.
    """
    order = dependency_order(sets)
    by_id = {cs.object_id: cs for cs in sets}
    solved_ids: list[str] = []
    placements: list[Placement] = []

    for object_id in order:
        cs = by_id.get(object_id)
        if cs is None:
            continue
        placement = solve(engine, cs, others=tuple(solved_ids))
        if engine.exists(object_id):
            engine.set_transform(object_id, transform_for(placement))
        placements.append(placement)
        solved_ids.append(object_id)

    return tuple(placements)


def transform_for(placement: Placement) -> Transform:
    """The engine :class:`~contracts.Transform` that realises a solved placement.

    Kept separate from :func:`solve` because a caller may re-derive the transform from a
    stored :class:`~contracts.Placement` — e.g. after :func:`constraints.satisfies`
    confirms it is still valid — without paying for a fresh solve.
    """
    up = placement.up.normalized()
    q_up = rotation_aligning(Vec3(0.0, 0.0, 1.0), up)
    y_after_up = q_up.rotate(Vec3(0.0, 1.0, 0.0))

    forward_in_plane = placement.forward - up * placement.forward.dot(up)
    if forward_in_plane.length() > 1e-6:
        f = forward_in_plane.normalized()
        sin_a = y_after_up.cross(f).dot(up)
        cos_a = max(-1.0, min(1.0, y_after_up.dot(f)))
        angle = math.atan2(sin_a, cos_a)
        rotation = (Quat.from_axis_angle(up, angle) * q_up).normalized()
    else:
        rotation = q_up

    return Transform(translation=placement.position, rotation=rotation, scale=Vec3(1.0, 1.0, 1.0))
