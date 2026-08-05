"""Stub — computable realism proxies. Explicitly not a "looks realistic" score.

See ``src/detail/README.md``. Gate A 11.3 splits verification authority: measurement decides
hard facts, the agent decides appearance. There is no computed metric for "looks realistic"
— research found no published one (``docs/research/domain.md``: "'Has bevels' / sharp-edge
ratio ... Partially ... inferred, not a published metric"), and inventing one would hand back
a number dressed up as a fact when it is actually an opinion with a decimal point. This module
returns only the individual, named proxies that ARE computable, and the caller (an agent
judging appearance, per Gate A 8.1/11.3) reads them alongside the render — it does not fold
them into one score.

Nothing here computes anything yet; the function raises until an implementer replaces the
body.

**Contract note (see the parent task's ``contractRequests``):** ``contracts.MetricKind`` has
seven members, of which only ``TRIANGLE_COUNT`` names one of this module's four documented
proxies directly. The other three — sharp-edge ratio, triangle aspect ratio, edge-length
uniformity — have no dedicated member. Until ``contracts`` grows one, an implementation must
reuse an existing ``MetricKind`` and carry the proxy's real name in ``Measurement.subject``/
``Measurement.detail`` instead of inventing an enum value of its own; ``report_test.py`` only
asserts that every returned ``kind`` is a genuine ``MetricKind`` member, not which one, so it
does not block on this gap.
"""

from __future__ import annotations

import math

from contracts import EngineProtocol, Measurement, MeshSnapshot, MetricKind

from .edges import select_bevel_edges

__all__ = ["realism_report"]


def realism_report(engine: EngineProtocol, object_id: str) -> tuple[Measurement, ...]:
    """Computable realism proxies for ``object_id`` — never a "looks realistic" verdict.

    Once implemented, this returns one :class:`contracts.Measurement` per proxy, at minimum:

    - **Sharp-edge ratio** — fraction of ``snapshot.edges()`` with two adjacent faces whose
      dihedral angle clears some "sharp" band (see :func:`detail.select_bevel_edges` for the
      same underlying angle computation; this is a read-only echo of it, not a re-derivation).
    - **Triangle aspect ratio** — a measure of how far the mesh's triangles are from
      equilateral (e.g. longest edge over shortest edge, averaged or worst-case); slivers are
      themselves a tell independent of anything about edges or materials.
    - **Edge-length uniformity** — spread of edge lengths across the mesh (e.g. coefficient of
      variation); a hand-authored or well-retopologised mesh does not have wildly
      inconsistent edge lengths, a naive generator often does.
    - **Triangle count** — ``MetricKind.TRIANGLE_COUNT``, the one proxy with an exact existing
      contract member; computed from ``engine.snapshot(object_id)`` directly, not imported
      from ``measure`` (this module does not depend on ``measure`` for anything computed
      fresh here — see ``.pipeline/modules.json``).

    None of these may be named, described, or documented as an overall realism, quality, or
    "does this look real" score — see ``report_test.py`` for the exact check. This function
    is read-only: it must never call a mutating ``EngineProtocol`` method.
    """
    snapshot = engine.snapshot(object_id)

    return (
        Measurement(
            kind=MetricKind.ANGLE,
            value=_sharp_edge_ratio(snapshot),
            unit="",
            subject=object_id,
            detail="sharp-edge ratio: fraction of edges at or above a 30-degree dihedral fold",
        ),
        Measurement(
            kind=MetricKind.DISTANCE,
            value=_triangle_aspect_ratio(snapshot),
            unit="",
            subject=object_id,
            detail="triangle aspect ratio: mean longest/shortest edge length per triangle",
        ),
        Measurement(
            kind=MetricKind.GAP_WIDTH,
            value=_edge_length_uniformity(snapshot),
            unit="",
            subject=object_id,
            detail="edge-length uniformity: coefficient of variation of edge lengths",
        ),
        Measurement(
            kind=MetricKind.TRIANGLE_COUNT,
            value=len(snapshot.triangles),
            unit="",
            subject=object_id,
            detail="triangle count of the evaluated mesh",
        ),
    )


def _sharp_edge_ratio(snapshot: MeshSnapshot) -> float:
    """Fraction of ``snapshot.edges()`` whose two adjacent faces fold at >= 30 degrees.

    Reuses :func:`detail.select_bevel_edges`'s own dihedral-angle computation with the
    convexity and hidden filters switched off — a read-only echo of the same formula, not
    a re-derivation (see this module's docstring).
    """
    edges = snapshot.edges()
    if not edges:
        return 0.0
    sharp = select_bevel_edges(snapshot, min_dihedral_deg=30.0, convex_only=False, exclude_hidden=False)
    return len(sharp.edge_indices) / len(edges)


def _triangle_aspect_ratio(snapshot: MeshSnapshot) -> float:
    """Mean, over every triangle, of its longest edge length over its shortest."""
    verts = snapshot.world_vertices()
    triangles = snapshot.triangles
    if not triangles:
        return 0.0
    ratios: list[float] = []
    for tri in triangles:
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        lengths = [(b - a).length(), (c - b).length(), (a - c).length()]
        shortest, longest = min(lengths), max(lengths)
        if shortest > 1e-9:
            ratios.append(longest / shortest)
    return sum(ratios) / len(ratios) if ratios else 0.0


def _edge_length_uniformity(snapshot: MeshSnapshot) -> float:
    """Coefficient of variation (stdev / mean) of world-space edge lengths.

    ``0`` means every edge is exactly the same length; a naive generator's wildly
    inconsistent edge lengths push this well above the value a hand-authored or
    well-retopologised mesh would show.
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
