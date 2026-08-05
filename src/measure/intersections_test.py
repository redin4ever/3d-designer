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
