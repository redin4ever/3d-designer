"""Planar-region re-triangulation — the decision half of the bevel cleanup (F-018).

Pure: takes a ``MeshSnapshot``, returns a triangle list over **exactly the same vertices**.
Never touches an engine — the mutating half lives in ``cleanup.py``, the same actor split
``apply.py``/``edges.py`` already uses (Rule 2).

**What it fixes, measured rather than assumed.** A real Blender bevel on a stair tread
measures a mean triangle aspect ratio of ~109 with a worst triangle of 1378:1. Almost none of
that is the bevel. Blender stores every mesh triangulated (``engine/_shared.py`` invariant #1)
and ear-clips the n-gons a bevel leaves behind, which turns a 1 m x 0.28 m face into needles
with a 0.72 mm base and two 992 mm sides — 47% of the total, and pure waste. This pass finds
the flat regions those needles live in and triangulates them properly instead. It takes the
tread to ~64 mean and 324:1 worst, and 324:1 is the bevel strip itself: a 4 mm strip along a
1 m edge, which no triangulation can improve and which only a visually wrong bevel width or a
triangle-count explosion could.

**The safety rule that makes it cheap to trust:** it never moves, adds or removes a vertex.
A region is only rebuilt if it can be rebuilt from its own boundary loop, so the vertex list
is untouched, the boundary is untouched, and a mesh that was closed and manifold before is
closed and manifold after — structurally, not because a check happened to pass.
"""

from __future__ import annotations

import math

from contracts import MeshSnapshot, Vec3

from ._polygon import MAX_EAR_CLIP, best_triangulation, signed_area

__all__ = ["retriangulate_planar_regions", "MAX_REGION_BOUNDARY"]

#: A region with more boundary vertices than this is left exactly as it was found. See
#: ``_polygon.MAX_EAR_CLIP`` — the search is cubic in boundary length, and Rule 6 counts a
#: stall as a death.
MAX_REGION_BOUNDARY = MAX_EAR_CLIP

Tri = tuple[int, int, int]


def retriangulate_planar_regions(
    snapshot: MeshSnapshot, *, coplanar_tolerance_deg: float = 0.5
) -> list[Tri]:
    """A better triangulation of ``snapshot`` over exactly the same vertices.

    Triangles whose face normals differ by less than ``coplanar_tolerance_deg`` across a
    shared edge are one *region*; each region is re-triangulated from its boundary loop and
    kept only if it measures better than what it replaced (see
    :func:`_polygon.best_triangulation`). Everything else is passed through untouched, so a
    mesh with nothing to gain comes back triangle-for-triangle identical — which is what lets
    ``cleanup_bevel_topology`` report an honest ``changed=False``.

    The tolerance defaults to half a degree rather than to zero because a bevel's own output
    is not bit-exactly planar: Blender's offsets land within about 1e-7 of the plane, and an
    exact test would see one flat face as a dozen unmergeable slivers. It stays far below the
    smallest angle a bevel profile itself produces (a two-segment 90-degree bevel folds by 30
    degrees per step), so no region ever swallows the bevel it is cleaning up.

    A region is declined, and left exactly as found, when:

    - it has fewer than two triangles (nothing to re-triangulate);
    - its triangles do not form a single closed boundary loop (a hole, a pinch, or a
      non-manifold fan — rebuilding it from one loop would change the surface);
    - it contains a vertex not on that loop (rebuilding from the boundary alone would delete
      that vertex, and something else's edge selection may index it);
    - its boundary is longer than :data:`MAX_REGION_BOUNDARY`;
    - nothing found beats the triangulation it already had.
    """
    triangles = [tuple(t) for t in snapshot.triangles]
    if len(triangles) < 2:
        return list(triangles)

    verts = snapshot.world_vertices()
    normals = [_face_normal(verts, t) for t in triangles]
    regions = _planar_regions(triangles, normals, coplanar_tolerance_deg)

    out: list[Tri] = []
    for members in regions:
        replacement = _rebuild(members, triangles, normals, verts)
        out.extend(replacement if replacement is not None else (triangles[i] for i in members))
    return out


def _rebuild(
    members: list[int], triangles: list[Tri], normals: list[Vec3 | None], verts: list[Vec3]
) -> list[Tri] | None:
    """A better triangulation of one region, or ``None`` to keep what it has."""
    if len(members) < 2:
        return None
    normal = next((normals[i] for i in members if normals[i] is not None), None)
    if normal is None:
        return None

    loop = _boundary_loop(members, triangles)
    if loop is None or not 3 <= len(loop) <= MAX_REGION_BOUNDARY:
        return None
    if {v for i in members for v in triangles[i]} != set(loop):
        return None  # an interior vertex; rebuilding from the boundary would delete it

    axis_u, axis_v = _plane_basis(normal)
    points = [(verts[i].dot(axis_u), verts[i].dot(axis_v)) for i in loop]
    if signed_area(points) < 0:  # the clipper and the DP both assume counter-clockwise
        loop = list(reversed(loop))
        points = list(reversed(points))

    position = {vertex: index for index, vertex in enumerate(loop)}
    current = [
        (position[a], position[b], position[c])
        for a, b, c in (triangles[i] for i in members)
    ]
    found = best_triangulation(points, current)
    if found is None:
        return None
    return [_wound(tuple(loop[i] for i in tri), verts, normal) for tri in found]


def _wound(tri: Tri, verts: list[Vec3], normal: Vec3) -> Tri:
    """``tri`` re-ordered to face the same way its region did.

    A flipped face is invisible in a solid viewport and then breaks booleans and exports
    (``DefectClass.FLIPPED_NORMAL``), so winding is fixed here rather than trusted.
    """
    a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
    return tri if (b - a).cross(c - a).dot(normal) >= 0 else (tri[0], tri[2], tri[1])


def _face_normal(verts: list[Vec3], tri: Tri) -> Vec3 | None:
    """The triangle's unit normal, or ``None`` when it is degenerate.

    Deliberately **not** ``Vec3.normalized()``, which raises below ``EPSILON`` (1e-4): a
    legitimate 2.4 mm x 3 mm bevel-corner triangle has a cross-product length around 7e-6 and
    would be thrown away — or, worse, would raise mid-pass. ``edges.py`` documents the same
    trap from the other direction.
    """
    a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
    normal = (b - a).cross(c - a)
    length = normal.length()
    if length <= 1e-15:
        return None
    return Vec3(normal.x / length, normal.y / length, normal.z / length)


def _planar_regions(
    triangles: list[Tri], normals: list[Vec3 | None], tolerance_deg: float
) -> list[list[int]]:
    """Connected groups of triangles that share an edge and lie in the same plane.

    Union-find rather than a flood fill: it is one pass over the edges with no recursion
    depth to blow on a large slab, and the group order below is derived from the lowest
    member index so the output is stable.
    """
    parent = list(range(len(triangles)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    incident: dict[tuple[int, int], list[int]] = {}
    for index, (i, j, k) in enumerate(triangles):
        for a, b in ((i, j), (j, k), (k, i)):
            incident.setdefault((a, b) if a < b else (b, a), []).append(index)

    threshold = math.cos(math.radians(tolerance_deg))
    for owners in incident.values():
        if len(owners) != 2:
            continue
        first, second = owners
        n1, n2 = normals[first], normals[second]
        if n1 is None or n2 is None or n1.dot(n2) < threshold:
            continue
        ra, rb = find(first), find(second)
        if ra != rb:
            parent[rb] = ra

    groups: dict[int, list[int]] = {}
    for index in range(len(triangles)):
        groups.setdefault(find(index), []).append(index)
    return sorted(groups.values(), key=lambda members: members[0])


def _boundary_loop(members: list[int], triangles: list[Tri]) -> list[int] | None:
    """The region's single closed boundary, as an ordered vertex ring, or ``None``.

    ``None`` means the region is not a simple disc — it has a hole, pinches at a vertex, or
    is wound inconsistently. Any of those makes "rebuild it from its boundary" the wrong
    operation rather than a harder one, so the caller keeps the region as it stands.
    """
    directed = set()
    for i in members:
        a, b, c = triangles[i]
        directed.update(((a, b), (b, c), (c, a)))

    successor: dict[int, int] = {}
    for a, b in sorted(directed):
        if (b, a) in directed:
            continue
        if a in successor:
            return None  # the boundary pinches at `a`: two ways out, no single ring
        successor[a] = b
    if not successor:
        return None

    start = min(successor)
    loop = [start]
    current = successor[start]
    while current != start:
        if current not in successor or len(loop) > len(successor):
            return None
        loop.append(current)
        current = successor[current]
    return loop if len(loop) == len(successor) else None


def _plane_basis(normal: Vec3) -> tuple[Vec3, Vec3]:
    """Any orthonormal pair spanning the plane ``normal`` is perpendicular to."""
    seed = Vec3(1.0, 0.0, 0.0) if abs(normal.x) < 0.9 else Vec3(0.0, 1.0, 0.0)
    axis = normal.cross(seed)
    length = axis.length()
    axis_u = Vec3(axis.x / length, axis.y / length, axis.z / length)
    return axis_u, normal.cross(axis_u)
