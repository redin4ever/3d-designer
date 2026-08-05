"""Residual checking — whether a solved placement still satisfies its constraints.

This is what makes a constraint **re-checkable** rather than fire-and-forget: a placement
solved before an upstream anchor moved can be re-measured against the *current* geometry
without re-solving, which is how a caller distinguishes "still valid" from "needs a
re-solve" at close to zero cost. Constraints are stored, not just applied (ADR-002), and
this function is half of what storing them buys — the other half is
:func:`constraints.solve` re-running from scratch.
"""

from __future__ import annotations

from contracts import ConstraintSet, EngineProtocol, Placement

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
    raise NotImplementedError("constraints.satisfies: not implemented")
