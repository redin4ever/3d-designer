"""Tests for the six single-object defect detectors.

Each is a genuinely different problem with a different repair — the ``DefectClass``
docstrings in ``contracts/measurement.py`` are explicit that lumping them into one "fix the
gaps" step is the most common mistake in this domain. These tests exist to keep the six
distinguishable at the point they are detected, not just at the point they are repaired.
"""

from __future__ import annotations

from contracts import DefectClass, EPSILON, Transform, Vec3
from measure import (
    find_boundary_holes,
    find_flipped_normals,
    find_loose_or_duplicate,
    find_non_manifold_edges,
    find_non_manifold_vertices,
    find_unapplied_transforms,
)
from testing import unit_cube


def test_closed_box_has_no_boundary_holes(engine) -> None:
    """A false positive here makes every clean import look broken and teaches an agent to
    distrust the one check ADR-005 calls non-negotiable."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    assert find_boundary_holes(engine, "box") == ()


def test_box_missing_one_face_reports_exactly_one_hole(engine) -> None:
    """A boundary hole is a BLOCKER — it fails on import into an engine or a slicer. Missing
    it here is a false negative on a defect that will hard-fail downstream instead of being
    caught and repaired first."""
    verts, faces = unit_cube()
    engine.create_mesh("open", verts, faces[:-1])

    holes = find_boundary_holes(engine, "open")

    assert len(holes) == 1
    assert holes[0].defect_class is DefectClass.BOUNDARY_HOLE
    assert holes[0].object_id == "open"


def test_edge_shared_by_three_faces_is_non_manifold(engine) -> None:
    """The repair for this (split the fan) only makes sense once it is named separately
    from every other kind of broken mesh; a detector that folds it into "has holes" gives
    the repair pass nothing to act on correctly."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, -1, 0), Vec3(0, 0, 1)]
    faces = [(0, 1, 2), (0, 1, 3), (0, 1, 4)]
    engine.create_mesh("fan", verts, faces)

    result = find_non_manifold_edges(engine, "fan")

    assert len(result) == 1
    assert result[0].defect_class is DefectClass.NON_MANIFOLD_EDGE
    assert result[0].object_id == "fan"


def test_two_triangles_meeting_at_a_vertex_is_non_manifold(engine) -> None:
    """Two cones touching at a point is invisible in a viewport and breaks booleans. The
    repair (duplicate the vertex, one copy per fan) is different from a non-manifold edge's
    repair, so this has to be its own detected class, not a variant of the other."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(-1, 0, 0), Vec3(0, -1, 0)]
    faces = [(0, 1, 2), (0, 3, 4)]
    engine.create_mesh("pinch", verts, faces)

    result = find_non_manifold_vertices(engine, "pinch")

    assert len(result) == 1
    assert result[0].defect_class is DefectClass.NON_MANIFOLD_VERTEX
    assert result[0].object_id == "pinch"


def test_duplicate_coincident_vertices_are_counted_correctly(engine) -> None:
    """Undercounting here means a repair pass welds "the duplicate" and leaves the rest
    sitting on top of a different vertex, silently. Vertex 3 duplicates vertex 0; vertices 5
    and 6 both duplicate vertex 4 — three duplicates total, none of them loose."""
    verts = [
        Vec3(0, 0, 0),  # 0 original A
        Vec3(1, 0, 0),  # 1 unrelated
        Vec3(0, 1, 0),  # 2 unrelated
        Vec3(0, 0, 0),  # 3 duplicate of 0
        Vec3(5, 5, 5),  # 4 original B
        Vec3(5, 5, 5),  # 5 duplicate of 4
        Vec3(5, 5, 5),  # 6 duplicate of 4
    ]
    faces = [(0, 1, 2), (3, 1, 2), (4, 1, 2), (5, 1, 2), (6, 1, 2)]
    engine.create_mesh("dup", verts, faces)

    result = find_loose_or_duplicate(engine, "dup", tolerance=EPSILON)

    assert len(result) == 3
    assert all(d.defect_class is DefectClass.LOOSE_OR_DUPLICATE for d in result)
    assert all(d.object_id == "dup" for d in result)


def test_unit_scale_has_no_unapplied_transform(engine) -> None:
    """A false positive here would flag every ordinary object in a scene as broken,
    teaching an agent to ignore the one warning that actually matters."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    assert find_unapplied_transforms(engine, "box") == ()


def test_non_unit_scale_reports_unapplied_transform(engine) -> None:
    """Unapplied non-uniform scale looks correct in the viewport and silently corrupts
    bevel width, boolean results and physics — the only way to catch it is to measure, never
    to look."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.set_transform("box", Transform(scale=Vec3(3, 1, 1)))

    result = find_unapplied_transforms(engine, "box")

    assert len(result) == 1
    assert result[0].defect_class is DefectClass.UNAPPLIED_TRANSFORM
    assert result[0].object_id == "box"


def test_closed_box_has_no_flipped_normals(engine) -> None:
    """A false positive here would flag every correctly-wound primitive as broken, which
    trains an agent to distrust or ignore the warning by the time it sees a real one."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    assert find_flipped_normals(engine, "box") == ()


def test_one_reversed_face_reports_a_flipped_normal(engine) -> None:
    """Invisible in solid shading with backface culling off, and it breaks booleans and
    exports — a render-based agent review would never catch this, which is the entire
    reason it has to be measured."""
    verts, faces = unit_cube()
    faces = list(faces)
    faces[0] = tuple(reversed(faces[0]))
    engine.create_mesh("flipped", verts, faces)

    result = find_flipped_normals(engine, "flipped")

    assert len(result) >= 1
    assert all(d.defect_class is DefectClass.FLIPPED_NORMAL for d in result)
    assert all(d.object_id == "flipped" for d in result)
