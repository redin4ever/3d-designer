"""Tests for the two cross-object checks and the one self-intersection check.

``find_clipping`` is the heart of the product: no geometry library can tell a post socketed
30mm into a deck (correct) apart from two posts wrongly overlapping by 30mm (a bug) — both
are identical BVH overlaps. The difference is declared intent
(:class:`contracts.JoineryIntent`), and these tests are what proves the tool honours that
distinction rather than silently treating every overlap the same way.
"""

from __future__ import annotations

import pytest

from contracts import DefectClass, JoineryIntent, Transform, Vec3
from measure import (
    find_boundary_holes,
    find_clipping,
    find_non_manifold_edges,
    find_self_intersections,
    find_visual_gaps,
)


def _box(engine, object_id: str, x: float) -> None:
    """A 1x1x1 cube centred at ``(x, 0, 0)`` — spans ``[x-0.5, x+0.5]`` on the x-axis."""
    engine.create_primitive(
        object_id, "cube", Vec3(1, 1, 1), Transform(translation=Vec3(x, 0, 0))
    )


def test_interpenetrating_boxes_report_clipping_with_magnitude(engine) -> None:
    """This magnitude is the number that tells a correct 30mm socket joint apart from a
    genuine collision downstream — get it wrong and every joinery decision built on it is
    wrong too."""
    _box(engine, "a", 0.0)  # spans [-0.5, 0.5]
    _box(engine, "b", 0.97)  # spans [0.47, 1.47] -> 0.03 overlap with a

    result = find_clipping(engine, [("a", "b")])

    assert len(result) == 1
    d = result[0]
    assert d.defect_class is DefectClass.PART_CLIPPING
    assert {d.object_id, d.other_object_id} == {"a", "b"}
    assert d.magnitude == pytest.approx(0.03, abs=1e-4)


def test_declared_joinery_intent_silences_a_matching_overlap(engine) -> None:
    """A post socketed 30mm into a deck and two posts wrongly overlapping by 30mm are
    identical BVH overlaps of identical magnitude — this is the one test proving the tool
    tells them apart by declared intent, never by inference from geometry."""
    _box(engine, "a", 0.0)
    _box(engine, "b", 0.97)  # 0.03 overlap
    intent = JoineryIntent(object_id="b", into_object_id="a", depth=0.05)

    result = find_clipping(engine, [("a", "b")], joinery=[intent])

    assert result == ()


def test_overlap_deeper_than_declared_intent_still_reports(engine) -> None:
    """A shallow declared intent must not blanket-excuse a deeper collision on the same
    pair — otherwise any joinery declaration becomes a way to silence real clipping anywhere
    between the two objects, not just at the declared depth."""
    _box(engine, "a", 0.0)
    _box(engine, "b", 0.97)  # 0.03 overlap
    shallow_intent = JoineryIntent(object_id="b", into_object_id="a", depth=0.01)

    result = find_clipping(engine, [("a", "b")], joinery=[shallow_intent])

    assert len(result) == 1
    assert result[0].defect_class is DefectClass.PART_CLIPPING


def test_joinery_intent_only_covers_the_pair_it_names(engine) -> None:
    """An implementation that applies any declared intent's depth to every overlapping
    pair in the batch — instead of checking which two specific objects the intent names —
    would silence real clipping anywhere in the scene the moment a single joint is
    declared legitimate. Two independent pairs prove the intent is matched per-pair, not
    applied globally: the pair it does not name must still report."""
    _box(engine, "a", 0.0)
    _box(engine, "b", 0.97)  # a-b overlap 0.03, NOT covered by the intent below
    _box(engine, "c", 5.0)
    _box(engine, "d", 5.97)  # c-d overlap 0.03, matches the intent below exactly
    intent = JoineryIntent(object_id="d", into_object_id="c", depth=0.05)

    result = find_clipping(engine, [("a", "b"), ("c", "d")], joinery=[intent])

    assert len(result) == 1
    found = result[0]
    assert found.defect_class is DefectClass.PART_CLIPPING
    assert {found.object_id, found.other_object_id} == {"a", "b"}


def test_touching_objects_report_no_clipping(engine) -> None:
    """A false positive on mere contact would flag every ordinary abutting joint in a scene
    as a defect, burying the genuine clipping cases in noise."""
    _box(engine, "a", 0.0)  # spans [-0.5, 0.5]
    _box(engine, "b", 1.0)  # spans [0.5, 1.5] -> touches a at x=0.5, zero overlap

    assert find_clipping(engine, [("a", "b")]) == ()


def test_visual_gap_is_reported_under_the_threshold(engine) -> None:
    """This defect passes every manifold and watertight check, because each part is
    individually fine — that is the entire reason it has to be its own detector rather than
    a side effect of the single-object checks."""
    _box(engine, "a", 0.0)  # ends at x=0.5
    _box(engine, "b", 1.005)  # starts at x=0.505 -> 5mm gap

    assert find_boundary_holes(engine, "a") == ()
    assert find_boundary_holes(engine, "b") == ()
    assert find_non_manifold_edges(engine, "a") == ()
    assert find_non_manifold_edges(engine, "b") == ()

    result = find_visual_gaps(engine, [("a", "b")], max_gap=0.01)

    assert len(result) == 1
    d = result[0]
    assert d.defect_class is DefectClass.VISUAL_GAP
    assert {d.object_id, d.other_object_id} == {"a", "b"}
    assert d.magnitude == pytest.approx(0.005, abs=1e-4)


def test_visual_gap_above_max_gap_threshold_is_not_reported(engine) -> None:
    """The same 5mm gap must not be flagged once the caller says a gap that size is
    acceptable — otherwise ``max_gap`` is decoration, not a real threshold."""
    _box(engine, "a", 0.0)
    _box(engine, "b", 1.005)  # same 5mm gap

    assert find_visual_gaps(engine, [("a", "b")], max_gap=0.001) == ()


def test_visual_gap_is_not_reported_for_objects_that_touch(engine) -> None:
    """The docstring requires a gap strictly greater than zero; an implementation using
    ``0 <= gap <= max_gap`` instead of ``0 < gap <= max_gap`` would flag every ordinary
    abutting joint in a scene as a visual gap, burying the genuine ones in noise — exactly
    the touching case ``find_clipping`` already has a dedicated test for, but
    ``find_visual_gaps`` does not."""
    _box(engine, "a", 0.0)  # spans [-0.5, 0.5]
    _box(engine, "b", 1.0)  # spans [0.5, 1.5] -> touches a at x=0.5, zero gap

    assert find_visual_gaps(engine, [("a", "b")], max_gap=0.5) == ()


def test_clean_mesh_has_no_self_intersections(engine) -> None:
    """A false positive here would block export of every ordinary clean mesh, since this
    defect class is a BLOCKER severity by default."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    assert find_self_intersections(engine, "box") == ()


def test_crossing_triangles_in_one_mesh_report_self_intersection(engine) -> None:
    """Two non-adjacent triangles of the same mesh sharing points in 3D is a BLOCKER — it
    fails on import into an engine or a slicer, and it is invisible to a render-based
    review, which is exactly why it has to be measured directly."""
    verts = [
        Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(0, 4, 0),   # triangle in z=0: x,y>=0, x+y<=4
        Vec3(1, 1, -2), Vec3(1, 1, 2), Vec3(3, 1, 0),  # triangle in y=1, piercing through it
    ]
    faces = [(0, 1, 2), (3, 4, 5)]
    engine.create_mesh("cross", verts, faces)

    result = find_self_intersections(engine, "cross")

    assert len(result) >= 1
    assert all(d.defect_class is DefectClass.SELF_INTERSECTION for d in result)
    assert all(d.object_id == "cross" for d in result)


# ------------------------------------------------- QA findings Q-008 and Q-009
#
# Both were confirmed by adversarial verification and both come from measuring boxes
# instead of geometry. ADR-005 gives these numbers authority over the agent's own
# judgement, so a confidently wrong one is worse than none.

def test_a_post_driven_through_a_deck_is_not_silenced_by_a_shallow_socket(engine) -> None:
    """The distinction the product claims no library can make.

    A 0.1m post driven 0.5m through a 1m deck shares (0.1, 0.1, 0.5) of overlap. The
    smallest of those is the post's own cross-section, which stays 0.1 however far through
    it goes — so comparing a declared 150mm socket against it reported a post clean through
    the deck as within intent.
    """
    from contracts import JoineryIntent, Transform

    engine.create_primitive("deck", "cube", Vec3(4.0, 4.0, 1.0),
                            Transform(translation=Vec3(0, 0, -0.5)))
    engine.create_primitive("post", "cube", Vec3(0.1, 0.1, 2.0),
                            Transform(translation=Vec3(0, 0, 0.5)))

    shallow = JoineryIntent(object_id="post", into_object_id="deck", depth=0.15)
    still_reported = find_clipping(engine, [("deck", "post")], joinery=[shallow])

    assert still_reported, "a post 0.5m through the deck was permitted by a 0.15m socket"
    assert "inserted 0.5" in still_reported[0].detail, still_reported[0].detail


def test_a_genuine_socket_deeper_than_declared_is_still_permitted(engine) -> None:
    """The other half: the fix must not start reporting joints that really are intended."""
    from contracts import JoineryIntent, Transform

    engine.create_primitive("deck", "cube", Vec3(4.0, 4.0, 1.0),
                            Transform(translation=Vec3(0, 0, -0.5)))
    engine.create_primitive("post", "cube", Vec3(0.1, 0.1, 2.0),
                            Transform(translation=Vec3(0, 0, 0.95)))  # 50mm in

    intent = JoineryIntent(object_id="post", into_object_id="deck", depth=0.06)
    assert find_clipping(engine, [("deck", "post")], joinery=[intent]) == ()


def test_two_rotated_beams_that_never_touch_report_a_real_distance(engine) -> None:
    """Both halves of the AABB defect in one fixture.

    Two 4m beams yawed 45 degrees and offset 1.4m have wildly overlapping bounding boxes
    and do not touch. Measured from boxes, the gap read 0.0 while find_clipping reported a
    0.1m interpenetration — so the agent was told to move correct geometry to fix a
    collision that does not exist, and simultaneously that a real 1.3m gap was closed.
    """
    import math

    from contracts import Quat, Transform

    yaw = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(45))
    engine.create_primitive("p", "cube", Vec3(0.1, 4.0, 0.1), Transform(rotation=yaw))
    engine.create_primitive("q", "cube", Vec3(0.1, 4.0, 0.1),
                            Transform(rotation=yaw, translation=Vec3(1.0, 1.0, 0.0)))

    from measure import distance, gap_width

    assert distance(engine, "p", "q").value > 0.5, "a real gap still reads as touching"
    assert gap_width(engine, "p", "q").value > 0.5


# ------------------------------------------------------- F-015: the quadratic blowup
#
# Measured against real Blender before this section existed: creating a 960-triangle
# sphere takes 0.006s and the self-intersection check that then runs automatically on it
# takes 6.5s and finds nothing — ~40% of a realistic 33-second session, on the default
# cadence, on the first non-trivial object anyone builds. These tests hold the pruning
# honest in both directions: much less work, and not one missed crossing.

#: Wall-clock ceiling for one ~1000-triangle self-intersection check. Deliberately loose
#: against the ~0.05s this actually costs after pruning, and still 6x under the 6.5s the
#: unpruned version took — a machine slow enough to fail this is slow enough that the
#: automatic check is unusable anyway.
SELF_INTERSECTION_CEILING_SECONDS = 1.0


def _uv_sphere(
    radius: float = 1.0, segments: int = 32, rings: int = 16, centre: Vec3 | None = None
) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    """A closed, correctly-wound UV sphere as explicit triangles.

    Built here rather than via ``engine.create_primitive``: ``FakeEngine`` approximates
    every non-planar primitive by its bounding box (12 triangles), which is exactly the
    kind of approximation that would make a density test pass while measuring nothing.
    32x16 is Blender's own default and yields 960 triangles, matching the mesh the 6.5s
    figure was measured on.
    """
    import math

    origin = centre or Vec3(0.0, 0.0, 0.0)
    verts: list[Vec3] = [Vec3(origin.x, origin.y, origin.z + radius)]
    for r in range(1, rings):
        phi = math.pi * r / rings
        z, rad = math.cos(phi) * radius, math.sin(phi) * radius
        for s in range(segments):
            theta = 2.0 * math.pi * s / segments
            verts.append(
                Vec3(origin.x + rad * math.cos(theta), origin.y + rad * math.sin(theta), origin.z + z)
            )
    verts.append(Vec3(origin.x, origin.y, origin.z - radius))
    south = len(verts) - 1

    def ring_vertex(r: int, s: int) -> int:
        return 1 + (r - 1) * segments + (s % segments)

    tris: list[tuple[int, int, int]] = []
    for s in range(segments):
        tris.append((0, ring_vertex(1, s), ring_vertex(1, s + 1)))
    for r in range(1, rings - 1):
        for s in range(segments):
            a, b = ring_vertex(r, s), ring_vertex(r, s + 1)
            c, d = ring_vertex(r + 1, s + 1), ring_vertex(r + 1, s)
            tris.append((a, b, c))
            tris.append((a, c, d))
    for s in range(segments):
        tris.append((south, ring_vertex(rings - 1, s + 1), ring_vertex(rings - 1, s)))
    return verts, tris


def test_a_clean_dense_mesh_reports_no_self_intersections(engine) -> None:
    """Correctness is not negotiable for speed. SELF_INTERSECTION is a BLOCKER by default,
    so one false positive on an ordinary 960-triangle sphere would block export of the
    first real object anybody builds — and it would do it on every automatic check."""
    verts, tris = _uv_sphere()
    engine.create_mesh("ball", verts, tris)
    assert len(tris) == 960, "the fixture stopped matching the mesh the 6.5s was measured on"

    assert find_self_intersections(engine, "ball") == ()


def test_a_self_intersecting_dense_mesh_is_still_detected_after_pruning(engine) -> None:
    """The failure a broad-phase introduces is a *missed* crossing, and a missed
    self-intersection is a defect the agent then exports. Two overlapping shells inside one
    mesh cross far from either shell's own neighbourhood, which is precisely the pair a
    naive "only test triangles near each other in index order" prune would drop."""
    verts_a, tris_a = _uv_sphere(radius=1.0, segments=16, rings=8)
    verts_b, tris_b = _uv_sphere(radius=1.0, segments=16, rings=8, centre=Vec3(1.0, 0.0, 0.0))
    offset = len(verts_a)
    verts = verts_a + verts_b
    tris = tris_a + [(a + offset, b + offset, c + offset) for a, b, c in tris_b]
    engine.create_mesh("twin", verts, tris)

    result = find_self_intersections(engine, "twin")

    assert result, "two interpenetrating shells in one mesh went undetected"
    assert all(d.defect_class is DefectClass.SELF_INTERSECTION for d in result)


def test_self_intersection_examines_a_small_fraction_of_the_naive_triangle_pairs(
    engine, monkeypatch
) -> None:
    """The performance fix, stated as the thing it actually changes: how many triangle
    pairs reach the exact intersection test. Without a ratio assertion here a later edit
    can quietly restore the full n^2 sweep and every other test still passes — the check
    just costs 40% of the session again."""
    import measure.intersections as intersections

    verts, tris = _uv_sphere()
    engine.create_mesh("ball", verts, tris)

    examined = 0
    real = intersections.triangles_intersect

    def counting(tri_a, tri_b):
        nonlocal examined
        examined += 1
        return real(tri_a, tri_b)

    monkeypatch.setattr(intersections, "triangles_intersect", counting)
    find_self_intersections(engine, "ball")

    naive = len(tris) * (len(tris) - 1) // 2
    assert examined < naive * 0.05, (
        f"{examined} of {naive} triangle pairs reached the exact test "
        f"({examined / naive:.1%}) — the broad-phase is not pruning"
    )


def test_self_intersection_on_a_thousand_triangle_mesh_stays_under_the_ceiling(engine) -> None:
    """This check runs automatically after every geometry change, and another agent is
    adding neighbour clipping to the same loop this round. At 6.5s per 960-triangle object
    the automatic cadence is unusable and the first thing an operator does is turn
    verification off — which is the product's whole premise, switched off."""
    import time

    verts, tris = _uv_sphere()
    engine.create_mesh("ball", verts, tris)

    started = time.perf_counter()
    result = find_self_intersections(engine, "ball")
    elapsed = time.perf_counter() - started

    assert result == ()
    assert elapsed < SELF_INTERSECTION_CEILING_SECONDS, (
        f"{len(tris)} triangles took {elapsed:.2f}s, ceiling is "
        f"{SELF_INTERSECTION_CEILING_SECONDS}s"
    )
