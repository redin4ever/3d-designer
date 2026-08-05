"""The constraint solver — turns a declarative constraint set into a concrete placement.

This is the module the product's headline number is about: raw x/y/z placement lands
within 2x of ground truth roughly 37% of the time even from a model purpose-trained for
spatial estimation; constraints resolved by a solver measure 91-95% (ADR-004). Every other
file in this package exists to support what happens here.
"""

from __future__ import annotations

from typing import Sequence

from contracts import ConstraintSet, EngineProtocol, Placement, Transform

__all__ = ["solve", "solve_all", "transform_for"]


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
    met raises :class:`~contracts.ConstraintError`. A SOFT constraint that cannot be met is
    satisfied on a best-effort basis; its shortfall is reported in
    :attr:`contracts.Placement.residuals` and
    :attr:`~contracts.Placement.satisfied_all_hard` stays ``True`` as long as every HARD
    constraint was actually met.

    A constraint naming an object that does not exist raises
    :class:`~contracts.ConstraintError` — never a bare ``KeyError`` — carrying the missing
    id and a ``suggestion`` (Gate A 4.2).

    ``others`` names sibling objects already placed earlier in this ``solve_all`` batch,
    for constraints (``spacing``, ``clear_of``) that need a neighbour's *solved* placement
    rather than its resting engine transform.
    """
    raise NotImplementedError("constraints.solve: not implemented")


def solve_all(engine: EngineProtocol, sets: Sequence[ConstraintSet]) -> tuple[Placement, ...]:
    """Solve every set in dependency order, each target resolved before its dependent.

    Raises :class:`~contracts.ConstraintError` with ``rule == CYCLE_RULE`` on a cyclic
    graph, via :func:`constraints.dependency_order` — the same failure, not a re-derived
    one, so a caller only ever handles one cycle-detection code path.
    """
    raise NotImplementedError("constraints.solve_all: not implemented")


def transform_for(placement: Placement) -> Transform:
    """The engine :class:`~contracts.Transform` that realises a solved placement.

    Kept separate from :func:`solve` because a caller may re-derive the transform from a
    stored :class:`~contracts.Placement` — e.g. after :func:`constraints.satisfies`
    confirms it is still valid — without paying for a fresh solve.
    """
    raise NotImplementedError("constraints.transform_for: not implemented")
