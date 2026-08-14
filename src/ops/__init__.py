"""``ops`` — the construction library: typed parametric operations, each carrying a
re-runnable acceptance query (ADR-004).

Not primitives (a railing takes ~140 of them and drift accumulates across every one) and
not whole-object composites (measured at -12.6% Exec@1 because the model must get a dozen
parameters right at once with no intermediate check). Every operation here is named,
validated on entry, and re-measurable on exit — that is what makes ADR-005's programmatic
definition-of-done possible.

Everything importable from ``ops`` is declared below. Nothing else is public; do not import
``ops.railing``, ``ops.stairs``, etc. directly from outside this package.
"""

from __future__ import annotations

from .architecture import add_floor, add_opening, add_wall
from .arrays import add_lod_chain, add_modular_kit, array_along
from .chimney import add_chimney
from .facade_ribs import add_facade_ribs
from .primitives import add_primitive
from .railing import add_railing
from .roof import add_gable_roof
from .surface_mounts import add_roof_window, add_wall_sign
from .registry import OP_SPECS, OPS
from .stairs import add_staircase
from .landing_stairs import add_staircase_to_landing
from .validation import acceptance_for, joinery_for, runtime_acceptance_for, validate_params

__all__ = [
    "OPS",
    "OP_SPECS",
    "add_primitive",
    "add_wall",
    "add_floor",
    "add_opening",
    "add_staircase",
    "add_staircase_to_landing",
    "add_railing",
    "add_gable_roof",
    "add_chimney",
    "add_roof_window",
    "add_wall_sign",
    "add_facade_ribs",
    "array_along",
    "add_lod_chain",
    "add_modular_kit",
    "validate_params",
    "acceptance_for",
    "runtime_acceptance_for",
    "joinery_for",
]
