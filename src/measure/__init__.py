"""``measure`` — the single authority on what is true about the geometry.

Computes the 7 metric queries and detects the 10 defect classes in
:class:`contracts.DefectClass`. Pure: it reads, it never mutates. Repair lives in ``gaps``,
not here (see ``docs/ARCHITECTURE.md``). This file is a barrel: re-exports only, no logic.
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
    # composition
    "inspect",
    "report",
    "evaluate",
    "is_watertight",
]
