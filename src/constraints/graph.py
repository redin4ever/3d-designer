"""Dependency ordering between constraint sets.

A :class:`~contracts.ConstraintSet` depends on every object its constraints target
(``ConstraintSet.depends_on()``). Solving out of order reads a target's pre-solve
position — wrong today, and silently wrong again the moment an upstream constraint
changes what "pre-solve" means. This module is the one place that decides a safe order,
and the one place that can tell a genuine cycle apart from a diamond that merely shares a
target twice.
"""

from __future__ import annotations

from typing import Sequence

from contracts import ConstraintSet

__all__ = ["dependency_order"]


def dependency_order(sets: Sequence[ConstraintSet]) -> tuple[str, ...]:
    """Object ids ordered so every target precedes its dependent.

    Raises :class:`~contracts.ConstraintError` with ``rule == CYCLE_RULE``
    (``contracts.CYCLE_RULE``) when the dependency graph has a cycle — ``A follows B`` and
    ``B follows A`` has no solvable order, and returning a partial or arbitrary order here
    would let :func:`constraints.solve_all` silently solve one of the two against stale
    geometry instead of failing loudly, per Gate A 4.2.

    A diamond — two nodes independently depending on the same shared target — is not a
    cycle: this orders a DAG, it does not require the dependency graph to be a single
    chain.
    """
    raise NotImplementedError("constraints.dependency_order: not implemented")
