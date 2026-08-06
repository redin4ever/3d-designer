"""Mesh-topology quality metrics and the bevel phase's acceptance query.

Split from ``report.py`` because these are *thresholdable* numbers with a gate hanging off
them, not report lines. ``report.py`` hands an agent four proxies to read beside a render
(Gate A 11.3); this file is what the phase gate re-runs to decide whether a bevel pass may be
left behind. ADR-012 removed the phase-promotion override at Gate B 1.1, so a failing query
is now the only thing standing between an unattended agent and a phase it cannot leave —
which makes an unreachable ceiling as bad a bug as a missing one.

``report.py`` imports the two metric functions from here rather than keeping its own copies:
two implementations of "triangle aspect ratio" that drift apart is how the same mesh ends up
simultaneously passing its gate and failing its report.
"""

from __future__ import annotations

import math

from contracts import AcceptanceQuery, Comparison, MeshSnapshot, MetricKind

__all__ = [
    "SLIVER_CEILING",
    "triangle_aspect_ratios",
    "mean_triangle_aspect_ratio",
    "edge_length_uniformity",
    "bevel_quality_acceptance",
]

SLIVER_CEILING = 80.0
"""The mean triangle aspect ratio a bevelled object may not exceed.

**Measured, not chosen.** On a stair tread built as ``ops.add_staircase`` builds one
(0.28 x 1.0 x 0.18 m), a real Blender bevel at this module's own default width measures 109
before the cleanup pass and 64 after it. 80 sits between the two with margin either side, so
the query fails the defect and passes the fix without sitting on a knife edge.

**What it is not.** It is not a universal statement about mesh quality. The aspect ratio a
correct bevel produces is roughly (bevelled edge length) / (bevel strip width), and since
``bevel_width_for`` scales width with object size, that ratio is close to scale-invariant and
close to ``1 / fraction`` — a 1 m cube bevelled at the default 0.4% measures around 144 after
cleanup and is not defective, it is simply an object that is nearly all bevel strip. Pass a
tighter or looser ``ceiling`` for a subject whose shape justifies one; do not read a single
number as "this mesh is good".
"""


def triangle_aspect_ratios(snapshot: MeshSnapshot) -> tuple[float, ...]:
    """Longest edge over shortest edge, one per triangle. ``1.0`` is equilateral.

    Degenerate triangles (a shortest edge at or below 1e-9 m, which real bevel output does
    contain) are skipped rather than reported as infinity: one zero-area triangle would
    otherwise make the mean infinite and take every threshold built on it with it.
    """
    verts = snapshot.world_vertices()
    ratios: list[float] = []
    for tri in snapshot.triangles:
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        lengths = ((b - a).length(), (c - b).length(), (a - c).length())
        shortest, longest = min(lengths), max(lengths)
        if shortest > 1e-9:
            ratios.append(longest / shortest)
    return tuple(ratios)


def mean_triangle_aspect_ratio(snapshot: MeshSnapshot) -> float:
    """The mean of :func:`triangle_aspect_ratios`. ``0.0`` for a mesh with no triangles."""
    ratios = triangle_aspect_ratios(snapshot)
    return sum(ratios) / len(ratios) if ratios else 0.0


def edge_length_uniformity(snapshot: MeshSnapshot) -> float:
    """Coefficient of variation (stdev / mean) of world-space edge length.

    ``0`` means every edge is exactly the same length. This one is *reported, not promised*:
    a 4 mm bevel on a 1 m object genuinely is a mesh with a 250:1 spread of edge lengths, and
    no re-triangulation can change that — only a different bevel width could.
    """
    verts = snapshot.world_vertices()
    edges = snapshot.edges()
    if not edges:
        return 0.0
    lengths = [(verts[a] - verts[b]).length() for a, b in edges]
    mean = sum(lengths) / len(lengths)
    if mean < 1e-9:
        return 0.0
    variance = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    return math.sqrt(variance) / mean


def bevel_quality_acceptance(
    object_id: str, *, ceiling: float = SLIVER_CEILING
) -> AcceptanceQuery:
    """The detail phase's machine-checkable definition of done for bevel topology.

    A re-runnable query against live geometry, never an agent's statement that it bevelled
    something: agents self-report false success in 13-89% of failures, and this is exactly the
    kind of "it worked" that looks identical to "it produced 1378:1 needles" from the outside.

    ``tolerance`` is deliberately loose (1% of the ceiling). Triangulation is discrete — one
    flipped edge moves the mean by a fraction of a point — and a hair-trigger tolerance would
    make the gate's verdict depend on which of two equally good triangulations Blender's
    vertex ordering happened to produce this run.
    """
    return AcceptanceQuery(
        query_id=f"{object_id}_bevel_topology",
        description=(
            "bevelled geometry is free of sliver triangles: mean triangle aspect ratio "
            f"at or under {ceiling:g} (1.0 is equilateral). Long thin triangles shade, bake "
            "and subdivide badly — the difference between geometry that is valid and "
            "geometry a modeller would accept."
        ),
        metric=MetricKind.TRIANGLE_ASPECT_RATIO,
        subject=object_id,
        expected=ceiling,
        tolerance=max(1e-4, ceiling * 0.01),
        comparison=Comparison.LTE,
    )
