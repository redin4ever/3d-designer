"""Tests for the planar re-triangulation that the bevel cleanup is built on.

Pure geometry, no engine: ``retriangulate_planar_regions`` takes a ``MeshSnapshot`` and
returns a new triangle list over **the same vertices**. That restriction is the whole safety
story for F-018 — a pass that cannot move, add or drop a vertex cannot open a hole, cannot
change the silhouette, and cannot invalidate a measurement taken before it ran. Everything
below either pins that restriction or pins the improvement that makes the pass worth running.
"""

from __future__ import annotations

import math

from contracts import MeshSnapshot, Vec3
from detail import mean_triangle_aspect_ratio, retriangulate_planar_regions
from testing import FakeEngine


def _snapshot(vertices, triangles) -> MeshSnapshot:
    return MeshSnapshot(object_id="m", vertices=list(vertices), triangles=list(triangles))


def _edge_use(triangles) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _fan_quad_strip() -> MeshSnapshot:
    """A 1 m x 4 mm planar strip with a 0.8 mm tab at one end, fanned from the far corner.

    This is F-018's shape in miniature. A bevel leaves flat faces as n-gons with sub-millimetre
    tabs where the corner patches meet them, and Blender ear-clips those n-gons into needles
    that span the whole face — measured at 1378:1 on a real stair tread. Fanning from vertex 0
    puts the tab's two vertices in a triangle with a corner 1 m away, which is exactly that
    failure; clipping the tab off first instead costs one small triangle and nothing else.
    """
    verts = [
        Vec3(0.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(1.0007, 0.0004, 0.0),
        Vec3(1.0, 0.004, 0.0),
        Vec3(0.0, 0.004, 0.0),
    ]
    return _snapshot(verts, [(0, 1, 2), (0, 2, 3), (0, 3, 4)])


# ------------------------------------------------------------------- it actually improves

def test_a_fan_triangulated_strip_is_measurably_improved() -> None:
    """This is F-018 in miniature. A strip triangulated by ear-clipping from a near-degenerate
    corner carries a needle whose aspect ratio is hundreds to one; a competent triangulation
    of the same five points does not. If this does not improve, nothing downstream of it can."""
    snap = _fan_quad_strip()
    before = mean_triangle_aspect_ratio(snap)

    triangles = retriangulate_planar_regions(snap)

    after = mean_triangle_aspect_ratio(_snapshot(snap.vertices, triangles))
    assert after < before, f"{before:.1f} -> {after:.1f}"


def test_it_never_returns_a_worse_triangulation_than_it_was_given() -> None:
    """The pass keeps whichever triangulation measures better, region by region, including
    the one it started with. Without that floor a "cleanup" could degrade a mesh that was
    already well triangulated — and it would do so silently, because nothing else re-measures
    between the bevel and the export."""
    # An already-optimal split of a square: two triangles across the short diagonal.
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(0, 1, 0)]
    snap = _snapshot(verts, [(0, 1, 2), (0, 2, 3)])
    before = mean_triangle_aspect_ratio(snap)

    triangles = retriangulate_planar_regions(snap)

    assert mean_triangle_aspect_ratio(_snapshot(verts, triangles)) <= before + 1e-9


# --------------------------------------------------------------------- it never breaks it

def test_every_vertex_survives_and_none_is_added() -> None:
    """The pass is allowed to change which triangles span the vertices and nothing else. A
    dropped vertex becomes a loose vertex (``DefectClass.LOOSE_OR_DUPLICATE``) or a crack; an
    added one changes the shape the user approved."""
    snap = _fan_quad_strip()

    triangles = retriangulate_planar_regions(snap)

    used = {i for tri in triangles for i in tri}
    assert used == set(range(len(snap.vertices)))
    assert all(0 <= i < len(snap.vertices) for tri in triangles for i in tri)


def test_a_closed_manifold_box_stays_closed_and_manifold(engine: FakeEngine) -> None:
    """A cleanup that improves aspect ratio while opening a hole is worse than the slivers it
    removed: a boundary hole is a BLOCKER at export, a sliver is not. Every edge must still
    bound exactly two triangles."""
    engine.create_primitive("box", "cube", Vec3(1.0, 2.0, 0.1))
    snap = engine.snapshot("box")
    assert all(c == 2 for c in _edge_use(snap.triangles).values()), "precondition"

    triangles = retriangulate_planar_regions(snap)

    assert all(c == 2 for c in _edge_use(triangles).values())


def test_face_winding_is_preserved_so_normals_do_not_flip(engine: FakeEngine) -> None:
    """A flipped face is invisible in a viewport with backface culling off and then breaks
    booleans and exports (``DefectClass.FLIPPED_NORMAL``). Re-triangulating a region must keep
    every new triangle wound the same way as the region it replaced."""
    engine.create_primitive("box", "cube", Vec3(1.0, 2.0, 0.1))
    snap = engine.snapshot("box")
    verts = snap.world_vertices()
    centre = snap.world_bounds().centre

    triangles = retriangulate_planar_regions(snap)

    for tri in triangles:
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        normal = (b - a).cross(c - a)
        # Every face of a convex box points away from its centre.
        assert normal.dot(((a + b + c) * (1.0 / 3.0)) - centre) > 0


def test_the_same_mesh_always_produces_the_same_triangulation() -> None:
    """Replay depends on it (ADR-002): the same operation against the same geometry must
    produce the same geometry. A triangulation that varies run to run would make an operation
    log non-deterministic and undo unsound."""
    snap = _fan_quad_strip()

    first = retriangulate_planar_regions(snap)
    second = retriangulate_planar_regions(snap)

    assert first == second


def test_a_region_with_interior_vertices_is_left_alone() -> None:
    """A planar region rebuilt from its boundary alone would silently drop any vertex in its
    interior. Rather than delete geometry, the pass declines the region — leaving a mesh
    slightly slivery is a recoverable outcome, deleting a vertex someone else's edge selection
    indexes is not."""
    # A square with a vertex at its centre, fanned: vertex 4 is interior to the region.
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(0, 1, 0), Vec3(0.5, 0.5, 0)]
    tris = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    snap = _snapshot(verts, tris)

    triangles = retriangulate_planar_regions(snap)

    assert sorted(map(sorted, triangles)) == sorted(map(sorted, tris))


def test_a_degenerate_triangle_does_not_take_the_whole_pass_down() -> None:
    """Real geometry contains zero-area triangles — a bevel produces them and so does every
    imported mesh with slivers. ``edges.py`` already learned this the hard way: a normal
    computed with ``Vec3.normalized()`` raises below ``EPSILON`` (1e-4), which is *larger*
    than a legitimate 2 mm bevel-corner triangle's cross product."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(2, 0, 0), Vec3(0, 1, 0)]
    snap = _snapshot(verts, [(0, 1, 2), (0, 3, 1)])

    triangles = retriangulate_planar_regions(snap)

    assert len(triangles) == 2


def test_a_mesh_with_no_coplanar_neighbours_is_returned_unchanged(engine: FakeEngine) -> None:
    """Nothing to merge means nothing to do. Returning a reordered-but-equivalent triangle
    list would make ``changed`` meaningless for the caller and churn the mesh on every replay."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)]
    tris = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]
    snap = _snapshot(verts, tris)

    assert retriangulate_planar_regions(snap) == [tuple(t) for t in tris]


def test_a_huge_planar_region_is_declined_rather_than_run_for_minutes() -> None:
    """The search is cubic in a region's boundary length. An unattended phase that stalls for
    minutes on one big floor slab is a worse failure than a slightly slivery floor slab —
    Rule 6 treats a stall as a death, so the pass bounds itself instead."""
    n = 400
    verts = [Vec3(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0)
             for i in range(n)]
    # Fanned from vertex 0, so every vertex sits on the region's boundary — the interior
    # vertex rule cannot be what declines this one; only the size bound can.
    tris = [(0, i, i + 1) for i in range(1, n - 1)]
    snap = _snapshot(verts, tris)

    triangles = retriangulate_planar_regions(snap)

    assert len(triangles) == n - 2
