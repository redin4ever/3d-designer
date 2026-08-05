"""``constraints`` — the solver that resolves the declarative placement vocabulary.

This is the single highest-value module in the product, and it has a number attached. A
model producing raw x/y/z coordinates lands within 2x of ground truth about 37% of the
time — even one purpose-trained for spatial estimation. A model emitting the twelve
declarative constraint types in ``contracts.ConstraintKind`` and letting this module
resolve them measures 91-95% (ADR-004). This barrel is that solver's public surface.

Constraints are **stored, not just applied**: :func:`solve` and :func:`solve_all` are
meant to be re-run whenever upstream geometry changes, and :func:`satisfies` is what lets
a caller tell "still valid" from "needs a re-solve" without paying for a fresh solve every
time — move the stair, and the railing constrained to its outer edge follows (ADR-002).
"""

from __future__ import annotations

from .anchors import AnchorResolution, resolve_anchor
from .graph import dependency_order
from .residual import satisfies
from .solver import solve, solve_all, transform_for

__all__ = [
    "AnchorResolution",
    "resolve_anchor",
    "solve",
    "solve_all",
    "transform_for",
    "dependency_order",
    "satisfies",
]
