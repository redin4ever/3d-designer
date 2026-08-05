"""``detail`` — the answer to the user's stated deal-breaker (Gate A 1.3, verbatim:
*"Still looks like glued boxes"*).

Four realism passes named at Gate A 8.4: heuristic edge treatment, surface detail (panel
lines, greebles), material realism (varied roughness, no pure black/white albedo), and a
report of computable proxies for what "realistic" can actually mean as a number. This file is
a barrel: re-exports only, no logic.
"""

from .apply import apply_edge_treatment
from .edges import EdgeSelection, bevel_width_for, select_bevel_edges
from .materials import clamp_albedo, vary_roughness
from .report import realism_report
from .results import DetailResult
from .surface import add_greebles, add_panel_lines

__all__ = [
    "EdgeSelection",
    "DetailResult",
    "select_bevel_edges",
    "bevel_width_for",
    "apply_edge_treatment",
    "add_panel_lines",
    "add_greebles",
    "vary_roughness",
    "clamp_albedo",
    "realism_report",
]
