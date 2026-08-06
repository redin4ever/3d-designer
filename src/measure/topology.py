"""The six single-object defect detectors. See ``src/measure/README.md``.

These are genuinely different problems with different repairs (``contracts.DefectClass``
docstrings are explicit about this); treating them as one "fix the gaps" step is the
most common mistake in this domain.

Pure: read-only over ``engine.snapshot(object_id)``. No mutating engine call.
"""

from __future__ import annotations

from typing import Sequence

from contracts import EPSILON, Defect, DefectClass, EngineProtocol

__all__ = [
    "find_boundary_holes",
    "find_non_manifold_edges",
    "find_non_manifold_vertices",
    "find_loose_or_duplicate",
    "find_flipped_normals",
    "find_unapplied_transforms",
]

Edge = tuple[int, int]
Triangle = tuple[int, int, int]


def _edge_occurrences(triangles: Sequence[Triangle]) -> dict[Edge, list[tuple[int, Edge]]]:
    """Every triangle occurrence of every undirected edge, keyed canonically.

    The one place edge enumeration happens by hand in this module — everything else
    (:func:`find_non_manifold_edges`, :func:`find_flipped_normals`) builds on this
    instead of re-deriving it (see ``CLAUDE.md``). ``MeshSnapshot.edges()`` gives the
    unique *set*; this additionally keeps which triangle, and which direction, each
    edge came from, which non-manifold and flipped-normal detection both need.
    """
    occurrences: dict[Edge, list[tuple[int, Edge]]] = {}
    for ti, (a, b, c) in enumerate(triangles):
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            occurrences.setdefault(key, []).append((ti, (u, v)))
    return occurrences


def find_boundary_holes(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per closed loop of edges each bounding exactly one face.

    ``DefectClass.BOUNDARY_HOLE`` — repair is to triangulate the loop.
    """
    snap = engine.snapshot(object_id)
    boundary = snap.boundary_edges()
    if not boundary:
        return ()

    adjacency: dict[int, list[int]] = {}
    for a, b in boundary:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    remaining = set(boundary)
    loop_count = 0
    while remaining:
        start, cur = next(iter(remaining))
        remaining.discard((start, cur))
        while True:
            nxt = None
            for candidate in adjacency.get(cur, ()):
                key = (cur, candidate) if cur < candidate else (candidate, cur)
                if key in remaining:
                    nxt = candidate
                    remaining.discard(key)
                    break
            if nxt is None or nxt == start:
                break
            cur = nxt
        loop_count += 1

    return tuple(
        Defect.of(DefectClass.BOUNDARY_HOLE, object_id, "closed loop of edges bounds no face")
        for _ in range(loop_count)
    )


def find_non_manifold_edges(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per edge with three or more incident faces.

    ``DefectClass.NON_MANIFOLD_EDGE`` — repair is to split the fan.
    """
    snap = engine.snapshot(object_id)
    occurrences = _edge_occurrences(snap.triangles)
    return tuple(
        Defect.of(
            DefectClass.NON_MANIFOLD_EDGE, object_id,
            f"edge {edge} has {len(hits)} incident faces",
        )
        for edge, hits in occurrences.items()
        if len(hits) >= 3
    )


def find_non_manifold_vertices(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per vertex whose incident faces form more than one fan — two
    cones touching at a point.

    ``DefectClass.NON_MANIFOLD_VERTEX`` — repair is to duplicate the vertex, one copy
    per fan.
    """
    snap = engine.snapshot(object_id)
    triangles = snap.triangles
    vertex_triangles: dict[int, list[int]] = {}
    for ti, tri in enumerate(triangles):
        for v in tri:
            vertex_triangles.setdefault(v, []).append(ti)

    defects = []
    for v, incident in vertex_triangles.items():
        if len(incident) <= 1:
            continue
        # Two incident triangles are in the same fan iff they share an edge through
        # v — i.e. two of their three vertices, not just v itself.
        adjacency = {ti: set() for ti in incident}
        for i in range(len(incident)):
            for j in range(i + 1, len(incident)):
                t1, t2 = incident[i], incident[j]
                if len(set(triangles[t1]) & set(triangles[t2])) >= 2:
                    adjacency[t1].add(t2)
                    adjacency[t2].add(t1)
        seen: set[int] = set()
        fans = 0
        for ti in incident:
            if ti in seen:
                continue
            fans += 1
            stack = [ti]
            seen.add(ti)
            while stack:
                cur = stack.pop()
                for nb in adjacency[cur]:
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        if fans > 1:
            defects.append(
                Defect.of(
                    DefectClass.NON_MANIFOLD_VERTEX, object_id,
                    f"vertex {v} has {fans} disconnected fans of incident faces",
                )
            )
    return tuple(defects)


def find_loose_or_duplicate(
    engine: EngineProtocol, object_id: str, tolerance: float = EPSILON
) -> tuple[Defect, ...]:
    """One :class:`Defect` per vertex/edge with no attached face, and one per coincident
    vertex not welded to its representative (vertices within ``tolerance`` of an
    earlier-indexed vertex are duplicates of it).

    ``DefectClass.LOOSE_OR_DUPLICATE``.
    """
    snap = engine.snapshot(object_id)
    referenced = {v for tri in snap.triangles for v in tri}
    verts = snap.vertices
    defects = []
    for i, v in enumerate(verts):
        if i not in referenced:
            defects.append(
                Defect.of(
                    DefectClass.LOOSE_OR_DUPLICATE, object_id,
                    f"vertex {i} is referenced by no face",
                )
            )
            continue
        for j in range(i):
            if (v - verts[j]).length() <= tolerance:
                defects.append(
                    Defect.of(
                        DefectClass.LOOSE_OR_DUPLICATE, object_id,
                        f"vertex {i} duplicates vertex {j}, not welded",
                    )
                )
                break
    return tuple(defects)


def find_flipped_normals(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per face whose winding is inconsistent with its neighbours.

    ``DefectClass.FLIPPED_NORMAL`` — invisible in solid shading with backface culling
    off, and it breaks booleans and exports.

    A properly-oriented manifold mesh traverses every shared edge in opposite
    directions from its two incident triangles. Two triangles that traverse their
    shared edge in the *same* direction disagree about winding, but with only that
    local signal a lone reversed face and its many correctly-wound neighbours look
    symmetric — each side can equally claim the other is wrong. Resolving that
    requires a majority vote over the whole connected mesh (see
    ``topology_test.py::test_one_reversed_face_reports_exactly_one_flipped_normal``,
    which a defect-per-conflicting-triangle-pair implementation over-reports): 2-colour
    the triangle-adjacency graph by parity of "same-direction" edges crossed, and the
    minority colour in each connected component is what disagrees with the rest.
    """
    snap = engine.snapshot(object_id)
    triangles = snap.triangles
    n = len(triangles)
    if n == 0:
        return ()

    occurrences = _edge_occurrences(triangles)
    adjacency: dict[int, list[tuple[int, bool]]] = {i: [] for i in range(n)}
    for hits in occurrences.values():
        for i in range(len(hits)):
            for j in range(i + 1, len(hits)):
                t1, d1 = hits[i]
                t2, d2 = hits[j]
                same_direction = d1 == d2
                adjacency[t1].append((t2, same_direction))
                adjacency[t2].append((t1, same_direction))

    color: list[int | None] = [None] * n
    flagged: set[int] = set()
    for start in range(n):
        if color[start] is not None:
            continue
        color[start] = 0
        component = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for neighbour, flips in adjacency[cur]:
                if color[neighbour] is None:
                    color[neighbour] = color[cur] ^ (1 if flips else 0)
                    component.add(neighbour)
                    stack.append(neighbour)
        by_color: dict[int, set[int]] = {0: set(), 1: set()}
        for ti in component:
            by_color[color[ti]].add(ti)
        if by_color[0] and by_color[1] and len(by_color[0]) != len(by_color[1]):
            minority = min(by_color.values(), key=len)
            flagged |= minority

    if not flagged:
        return ()

    # Group the flagged triangles into connected sub-components (any shared edge) so
    # one reversed original face — however many triangles it triangulates to —
    # produces exactly one defect, not one per triangle.
    grouped: set[int] = set()
    defects = []
    for ti in sorted(flagged):
        if ti in grouped:
            continue
        group = {ti}
        stack = [ti]
        grouped.add(ti)
        while stack:
            cur = stack.pop()
            for neighbour, _ in adjacency[cur]:
                if neighbour in flagged and neighbour not in grouped:
                    grouped.add(neighbour)
                    group.add(neighbour)
                    stack.append(neighbour)
        defects.append(
            Defect.of(
                DefectClass.FLIPPED_NORMAL, object_id,
                f"triangle(s) {sorted(group)} wind opposite to their neighbours",
            )
        )
    return tuple(defects)


def find_unapplied_transforms(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """A single :class:`Defect` if the object carries non-unit scale not baked into mesh
    data (see :meth:`contracts.Transform.has_unapplied_scale`); empty otherwise.

    ``DefectClass.UNAPPLIED_TRANSFORM`` — looks correct in the viewport and silently
    corrupts bevel width, boolean results and physics.
    """
    transform = engine.snapshot(object_id).transform
    if not transform.has_unapplied_scale():
        return ()
    return (
        Defect.of(
            DefectClass.UNAPPLIED_TRANSFORM, object_id,
            f"scale {transform.scale.as_tuple()} is not baked into mesh data",
        ),
    )
