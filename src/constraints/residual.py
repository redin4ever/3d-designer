"""Residual checking — whether a solved placement still satisfies its constraints.

This is what makes a constraint **re-checkable** rather than fire-and-forget: a placement
solved before an upstream anchor moved can be re-measured against the *current* geometry
without re-solving, which is how a caller distinguishes "still valid" from "needs a
re-solve" at close to zero cost. Constraints are stored, not just applied (ADR-002), and
this function is half of what storing them buys — the other half is
:func:`constraints.solve` re-running from scratch.

Reuses the same per-kind requirement functions ``solver.py`` applies (``_position.py``,
``_orientation.py``) so a placement ``solve`` just produced can never fail its own
``satisfies`` check — the two would otherwise be two independent opinions about what a
constraint means, free to drift apart.
"""

from __future__ import annotations

from contracts import ConstraintSet, EngineProtocol, Placement

from ._orientation import FORWARD_KINDS, UP_KINDS, forward_for, up_for
from ._position import POSITION_KINDS, position_effect, position_residual

__all__ = ["satisfies"]


def satisfies(
    engine: EngineProtocol, cs: ConstraintSet, placement: Placement
) -> tuple[tuple[str, float], ...]:
    """Per-constraint residual of ``placement`` against ``cs``, measured against the
    engine's *current* geometry — not whatever geometry was current when ``placement`` was
    originally solved.

    Returns ``()`` when every constraint is met within its tolerance. A non-empty entry is
    ``(description, unsatisfied amount)`` — always a non-negative magnitude, never a signed
    value a caller could misread as "which way to move it", matching
    :attr:`contracts.Placement.residuals`.
    """
    if cs.uses_escape_hatch:
        return ()

    residuals: list[tuple[str, float]] = []
    for c in cs.constraints:
        if c.kind in POSITION_KINDS:
            effect = position_effect(engine, cs.object_id, c, placement.position)
            diff = position_residual(placement.position, effect)
        elif c.kind in FORWARD_KINDS:
            required = forward_for(engine, c)
            diff = (required - placement.forward.normalized()).length()
        elif c.kind in UP_KINDS:
            required = up_for(engine, c)
            diff = (required - placement.up.normalized()).length()
        else:  # pragma: no cover - every ConstraintKind is one of the above families
            diff = 0.0
        if diff > c.tolerance:
            residuals.append((f"{c.kind.value} -> {c.target.key()}", diff))

    return tuple(residuals)
