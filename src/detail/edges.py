"""Stub — which edges plausibly catch light, and how wide to bevel them.

See ``src/detail/README.md`` for the full contract. This is the answer to the user's stated
deal-breaker (Gate A 1.3, verbatim: *"Still looks like glued boxes"*) and the highest-leverage
single lever the research turned up: a perfectly sharp CAD edge produces a hard, artificial
specular break; even a tiny bevel produces the highlight line a viewer reads as real material.
Gate A 8.3 chose the heuristic option over bevelling everything, because the same research
warns that uniform bevelling is itself an artificiality tell — so this file's whole job is
picking a **proper subset**. An implementation that returns every edge has reintroduced the
exact thing the user rejected, and ``edges_test.py`` fails it on purpose.

Nothing here computes anything yet — every function raises until an implementer replaces the
body. ``EdgeSelection`` is real, constructed data (a frozen dataclass has no body to
implement).

Pure: neither function here may call a mutating ``EngineProtocol`` method. Both take a
``MeshSnapshot`` directly, not an engine handle — selection and width are decisions made from
geometry already in hand, never from a live mutation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from contracts import MeshSnapshot, Vec3

__all__ = ["EdgeSelection", "select_bevel_edges", "bevel_width_for"]


@dataclass(frozen=True, slots=True)
class EdgeSelection:
    """The result of one selection pass over ``snapshot.edges()``.

    ``edge_indices`` are positions into ``snapshot.edges()`` — the canonical ordering that
    ``MeshSnapshot.edges()`` documents as the entire contract between a selection here and
    the engine's ``ModifierOps.bevel_edges``. An index outside ``range(len(snapshot.edges()))``
    would silently bevel whatever edge happens to sit at that position on the *engine* side
    (or nothing at all), with no error — ``edges_test.py`` asserts every returned index is
    in range for exactly this reason.

    ``reasons`` is parallel to ``edge_indices`` (same length, same order) — one short string
    per selected edge naming why it qualified (e.g. its dihedral angle and whether it read as
    convex/exposed). This is the audit trail: a heuristic that can silently over- or
    under-select needs to be inspectable, per Gate A 4.2 ("what rule it broke").

    ``rejected`` counts edges that were *considered* — i.e. had two adjacent faces and
    therefore a computable dihedral angle — and did not qualify. It is not a count of every
    edge that failed to make it into ``edge_indices`` for any reason (a boundary edge with
    only one adjacent face was never a candidate at all, and does not inflate this number).
    """

    edge_indices: tuple[int, ...]
    reasons: tuple[str, ...]
    rejected: int


def select_bevel_edges(
    snapshot: MeshSnapshot,
    *,
    min_dihedral_deg: float = 30.0,
    convex_only: bool = True,
    exclude_hidden: bool = True,
) -> EdgeSelection:
    """Pick the subset of ``snapshot.edges()`` that would plausibly catch light.

    An edge is a *candidate* only if it has exactly two adjacent triangles (a boundary edge,
    with one, has no second face to measure a dihedral angle against, and is never selected).
    Among candidates, one qualifies only if it passes every filter currently enabled:

    1. **Sharp enough.** The dihedral angle — the angle between the two adjacent triangles'
       face normals, ``acos(dot(n1, n2))`` in degrees, ``[0, 180]`` — must be at least
       ``min_dihedral_deg``. ``0`` means the two triangles are coplanar (perfectly flat,
       nothing to bevel); the closer to ``180``, the sharper the fold. This is the one
       published-adjacent formula in this domain (``contracts.MeshSnapshot`` edges +
       Blender's own "Edge Angle" node use exactly this dot-product construction) — do not
       invent a different angle measure.

    2. **Convex, when ``convex_only`` is set** (the default). Sharp is not enough on its own:
       a re-entrant crease (the inside corner of an open box, e.g. where two interior walls
       meet) is exactly as sharp as an outer corner but never catches a highlight the way an
       outward corner does, and Gate A 8.3 asks for edges that would. Convexity needs a sign,
       which the raw dihedral angle above does not carry: take the edge's two candidate
       triangles, and for either one, the vertex of the *other* triangle that is not on the
       shared edge. The edge is convex iff that vertex lies on the *inward* side of the first
       triangle's own plane — i.e. ``dot(n1, other_vertex - edge_point) < 0``. (Sanity check
       against a primitive known to be entirely convex, e.g. any edge of an axis-aligned box:
       this test returns negative for every one of its twelve edges.) When ``convex_only`` is
       ``False`` this filter is skipped entirely — a concave crease that is otherwise sharp
       enough and exposed enough qualifies too.

    3. **Exposed, when ``exclude_hidden`` is set** (the default). An edge is *hidden* — and
       excluded — when the average of its two adjacent triangles' face-normal Z components is
       negative, i.e. the edge faces predominantly away from world up (``contracts.WORLD_UP``).
       This is a deliberately cheap, deterministic proxy for "would this edge plausibly catch
       light from a typical scene", standing in for real occlusion testing (which needs a
       renderer this module does not have): the underside of an object resting on a surface is
       the one region a heuristic edge-treatment pass can rule out for free, and doing so is
       exactly what keeps a plain box from selecting all twelve of its edges (see
       ``edges_test.py::test_a_plain_cube_selects_a_proper_subset`` — a cube has four such
       edges, all on its bottom face, out of twelve). When ``exclude_hidden`` is ``False`` this
       filter is skipped and a hidden-but-otherwise-qualifying edge is included.

    Every edge that was a candidate (had two adjacent faces) but failed one of the *enabled*
    filters counts toward ``EdgeSelection.rejected``.
    """
    edges = snapshot.edges()
    verts = snapshot.world_vertices()
    adjacency = _build_adjacency(snapshot.triangles)
    normals = [_triangle_normal(verts, tri) for tri in snapshot.triangles]

    selected: list[int] = []
    reasons: list[str] = []
    rejected = 0

    for idx, (u, v) in enumerate(edges):
        occurrences = adjacency.get((u, v), ())
        if len(occurrences) != 2:
            # A boundary edge (one adjacent face) has no dihedral angle to measure and
            # was never a candidate — it must not inflate `rejected` (see docstring).
            continue

        (t1, _opp1), (t2, opp2) = occurrences
        n1, n2 = normals[t1], normals[t2]
        cosine = max(-1.0, min(1.0, n1.dot(n2)))
        dihedral_deg = math.degrees(math.acos(cosine))

        if dihedral_deg < min_dihedral_deg:
            rejected += 1
            continue

        if convex_only:
            edge_point = verts[u]
            other_vertex = verts[opp2]
            is_convex = n1.dot(other_vertex - edge_point) < 0.0
            if not is_convex:
                rejected += 1
                continue

        if exclude_hidden:
            average_z = (n1.z + n2.z) / 2.0
            if average_z < 0.0:
                rejected += 1
                continue

        selected.append(idx)
        tags = [f"dihedral={dihedral_deg:.1f}deg"]
        if convex_only:
            tags.append("convex")
        if exclude_hidden:
            tags.append("exposed")
        reasons.append(" ".join(tags))

    return EdgeSelection(edge_indices=tuple(selected), reasons=tuple(reasons), rejected=rejected)


def _triangle_normal(verts: list[Vec3], tri: tuple[int, int, int]) -> Vec3:
    a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
    return (b - a).cross(c - a).normalized()


def _build_adjacency(
    triangles,
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Edge -> the (triangle index, opposite-vertex index) pairs that touch it.

    Built once per call over ``triangles`` rather than recomputed per edge — the same
    guidance ``CLAUDE.md`` gives for this file.
    """
    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for ti, tri in enumerate(triangles):
        for a, b, opposite in (
            (tri[0], tri[1], tri[2]),
            (tri[1], tri[2], tri[0]),
            (tri[2], tri[0], tri[1]),
        ):
            key = (a, b) if a < b else (b, a)
            adjacency.setdefault(key, []).append((ti, opposite))
    return adjacency


def bevel_width_for(
    snapshot: MeshSnapshot,
    *,
    fraction: float = 0.004,
    minimum: float = 0.0005,
    maximum: float = 0.01,
) -> float:
    """Bevel width scaled to the object's real-world size, in metres.

    A 2 mm bevel on a doorknob and the same 2 mm bevel on a warehouse wall are different
    amounts of wrong — the first is plausible wear, the second is imperceptible to the point
    of pointless. The width returned here is ``fraction`` of some characteristic size of the
    object's world-space bounds (``snapshot.world_bounds()``) — e.g. the longest axis, the
    diagonal, or the cube root of the bounding volume are all defensible choices of
    "characteristic size" and this contract does not mandate one; ``edges_test.py`` is
    written to hold for any of them (its example objects are picked so that every reasonable
    choice of characteristic size lands on the same side of both clamps).

    The result is always clamped into ``[minimum, maximum]`` and is always strictly positive
    — a width of exactly ``0`` is rejected by ``ModifierOps.bevel_edges`` at the engine layer
    (``EngineError`` on ``width <= 0``), so returning it here would just move the failure one
    call later with no more information attached.

    A fixed width that ignores ``snapshot`` entirely satisfies none of the above except "is
    positive", and is exactly the failure this function exists to prevent — see
    ``edges_test.py::test_a_fixed_width_regardless_of_size_is_rejected`` and its two
    neighbours, which pin a tiny and a huge object to the ``minimum``/``maximum`` clamps
    respectively. A constant cannot equal both.

    Characteristic size chosen here: the longest axis of ``snapshot.world_bounds()``. A
    doorknob and a warehouse wall differ enormously on this measure while an axis-aligned
    box's diagonal or cube-root-of-volume would land in the same place for these examples
    — any of the three satisfies this contract (see docstring above).
    """
    size = snapshot.world_bounds().size
    characteristic = max(size.x, size.y, size.z)
    width = fraction * characteristic
    return max(minimum, min(maximum, width))
