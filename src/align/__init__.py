"""``align`` — one-shot geometric snaps: the IMMEDIATE-SNAP counterpart to ``constraints``.

``constraints`` expresses a *standing relationship* that re-solves when an anchor moves
(ADR-002): constrain a railing plumb to a stair, move the stair, the railing re-solves.
``align`` performs the identical geometric correction *once, right now*, with no stored
relationship left behind — the tool for "these two walls should be parallel" as a single
correction, not an ongoing rule. Same maths (this package calls directly into
``constraints.solve``/``transform_for`` wherever a ``ConstraintKind`` already covers the
operation exactly — ``make_plumb``, ``make_flush``, and ``make_coplanar``'s default face),
different lifecycle.

Everything importable from ``align`` is declared below. Nothing else is public; do not
import ``align.orientation``, ``align.position``, etc. directly from outside this package.
"""

from __future__ import annotations

from .grid import snap_to_grid
from .orientation import make_parallel, make_perpendicular, make_plumb, measure_angle, set_angle
from .position import make_coplanar, make_flush
from .registry import ALIGN_SPECS
from .results import AlignResult

__all__ = [
    "AlignResult",
    "make_parallel",
    "make_perpendicular",
    "make_coplanar",
    "make_plumb",
    "make_flush",
    "snap_to_grid",
    "set_angle",
    "measure_angle",
    "ALIGN_SPECS",
]
