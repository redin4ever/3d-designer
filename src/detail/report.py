"""Computable realism proxies. Explicitly not a "looks realistic" score.

See ``src/detail/README.md``. Gate A 11.3 splits verification authority: measurement decides
hard facts, the agent decides appearance. There is no computed metric for "looks realistic"
— research found no published one (``docs/research/domain.md``: "'Has bevels' / sharp-edge
ratio ... Partially ... inferred, not a published metric"), and inventing one would hand back
a number dressed up as a fact when it is actually an opinion with a decimal point. This module
returns only the individual, named proxies that ARE computable, and the caller (an agent
judging appearance, per Gate A 8.1/11.3) reads them alongside the render — it does not fold
them into one score.

**The contract gap is closed.** ``contracts.MetricKind`` now has ``SHARP_EDGE_RATIO``,
``TRIANGLE_ASPECT_RATIO`` and ``EDGE_LENGTH_UNIFORMITY`` — filed as a contract request twice
and deferred twice, added for Gate B 3.4. Until they existed this file reused
``ANGLE``/``DISTANCE``/``GAP_WIDTH`` and carried each proxy's real name in
``Measurement.detail``, which meant a caller could not filter or threshold on them and
nothing could express "this bevel is too slivery" as an acceptance query. It now names the
real members, and ``quality.py`` owns the two computations that a gate also thresholds, so
the report and the gate cannot drift apart.
"""

from __future__ import annotations

from contracts import EngineProtocol, Measurement, MeshSnapshot, MetricKind

from .edges import select_bevel_edges
from .quality import edge_length_uniformity, mean_triangle_aspect_ratio

__all__ = ["realism_report"]


def realism_report(engine: EngineProtocol, object_id: str) -> tuple[Measurement, ...]:
    """Computable realism proxies for ``object_id`` — never a "looks realistic" verdict.

    One :class:`contracts.Measurement` per proxy:

    - **Sharp-edge ratio** — fraction of ``snapshot.edges()`` with two adjacent faces whose
      dihedral angle clears the "sharp" band (:func:`detail.select_bevel_edges`'s own angle
      computation with the convexity and exposure filters off — a read-only echo of it, not a
      re-derivation).
    - **Triangle aspect ratio** — how far the mesh's triangles are from equilateral. Slivers
      are a tell independent of anything about edges or materials, and this is the number
      Gate B 3.4 made a deliverable (see :data:`detail.SLIVER_CEILING`).
    - **Edge-length uniformity** — spread of edge lengths. A hand-authored or
      well-retopologised mesh does not have wildly inconsistent edge lengths; a naive
      generator often does.
    - **Triangle count** — computed from ``engine.snapshot(object_id)`` directly, not
      imported from ``measure`` (see ``.pipeline/modules.json``).

    None of these may be named, described, or documented as an overall realism, quality, or
    "does this look real" score — see ``report_test.py`` for the exact check. This function
    is read-only: it never calls a mutating ``EngineProtocol`` method.
    """
    snapshot = engine.snapshot(object_id)

    return (
        Measurement(
            kind=MetricKind.SHARP_EDGE_RATIO,
            value=_sharp_edge_ratio(snapshot),
            unit="",
            subject=object_id,
            detail="fraction of edges at or above a 30-degree dihedral fold",
        ),
        Measurement(
            kind=MetricKind.TRIANGLE_ASPECT_RATIO,
            value=mean_triangle_aspect_ratio(snapshot),
            unit="",
            subject=object_id,
            detail="mean longest/shortest edge length per triangle; 1.0 is equilateral",
        ),
        Measurement(
            kind=MetricKind.EDGE_LENGTH_UNIFORMITY,
            value=edge_length_uniformity(snapshot),
            unit="",
            subject=object_id,
            detail="coefficient of variation of edge lengths; 0 is perfectly even",
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
    """Fraction of ``snapshot.edges()`` whose two adjacent faces fold at >= 30 degrees."""
    edges = snapshot.edges()
    if not edges:
        return 0.0
    sharp = select_bevel_edges(
        snapshot, min_dihedral_deg=30.0, convex_only=False, exclude_hidden=False
    )
    return len(sharp.edge_indices) / len(edges)
