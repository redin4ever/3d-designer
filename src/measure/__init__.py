"""``measure`` — the single authority on what is true about the geometry.

Computes the 7 metric queries and detects the 10 defect classes in
:class:`contracts.DefectClass`. Pure: it reads, it never mutates. Repair lives in ``gaps``,
not here (see ``docs/ARCHITECTURE.md``). ``MEASURE_SPECS`` is how an agent reaches any of
it — without that constant every function below is implemented, green and uncallable. This
file is a barrel: re-exports only, no logic.
"""

from .intersections import find_clipping, find_self_intersections, find_visual_gaps
from .metrics import (
    angle_between,
    bounds,
    dimensions,
    distance,
    gap_width,
    triangle_count,
    volume,
)
from .neighbours import DEFAULT_MAX_GAP, neighbour_defects, neighbour_pairs
from .registry import MEASURE_SPECS, bind_engine
from .report import evaluate, inspect, is_watertight, report
from .topology import (
    find_boundary_holes,
    find_flipped_normals,
    find_loose_or_duplicate,
    find_non_manifold_edges,
    find_non_manifold_vertices,
    find_unapplied_transforms,
)

__all__ = [
    # metrics
    "bounds",
    "dimensions",
    "distance",
    "angle_between",
    "gap_width",
    "volume",
    "triangle_count",
    # topology
    "find_boundary_holes",
    "find_non_manifold_edges",
    "find_non_manifold_vertices",
    "find_loose_or_duplicate",
    "find_flipped_normals",
    "find_unapplied_transforms",
    # intersections
    "find_self_intersections",
    "find_clipping",
    "find_visual_gaps",
    # neighbour-scoped pairwise checks
    "neighbour_pairs",
    "neighbour_defects",
    "DEFAULT_MAX_GAP",
    # composition
    "inspect",
    "report",
    "evaluate",
    "is_watertight",
    # the mcp tool surface
    "MEASURE_SPECS",
    "bind_engine",
]
