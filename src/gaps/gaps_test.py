"""Tests for the corrective half of ``measure``.

Every repair here is verified with the matching ``measure`` detector, never with the
repair's own return value — a repair that reports success while leaving the defect in
place is exactly the failure mode this module exists to avoid. See ``CLAUDE.md``.
"""

from __future__ import annotations

import pytest

from contracts import DefectClass, RepairOutcome, ToolRole, Transform, Vec3
from gaps import (
    GAPS_SPECS,
    close_visual_gap,
    fill_boundary_holes,
    fix_normals,
    merge_shells,
    remove_loose,
    repair,
    split_non_manifold,
    weld_duplicates,
)
from measure import (
    find_boundary_holes,
    find_flipped_normals,
    find_loose_or_duplicate,
    find_non_manifold_vertices,
    gap_width,
)
from testing import unit_cube


# --------------------------------------------------------------- fill_boundary_holes

def test_fill_boundary_holes_closes_a_hole_verified_by_the_detector(engine) -> None:
    """The repair's own ``fixed`` count is not proof enough — the detector going quiet
    afterwards is (see module docstring)."""
    verts, faces = unit_cube()
    engine.create_mesh("open", verts, faces[:-1])
    assert find_boundary_holes(engine, "open") != ()

    outcome = fill_boundary_holes(engine, "open")

    assert outcome.fixed == 1
    assert find_boundary_holes(engine, "open") == ()


def test_fill_boundary_holes_with_max_sides_reports_a_skip_not_a_bare_zero(engine) -> None:
    """A bare 0 cannot distinguish "nothing to do" from "found work and refused it" — a
    caller would report a clean mesh that still has a hole."""
    verts, faces = unit_cube()
    engine.create_mesh("open4", verts, faces[:-1])  # the removed face is a quad

    outcome = fill_boundary_holes(engine, "open4", max_sides=3)

    assert outcome.fixed == 0
    assert outcome.skipped == 1
    assert outcome.reason != ""
    assert find_boundary_holes(engine, "open4") != ()


# --------------------------------------------------------------------- weld_duplicates

def test_weld_duplicates_drops_the_count_and_the_detector_goes_quiet(engine) -> None:
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 0)]  # 3 duplicates 0
    faces = [(0, 1, 2), (3, 1, 2)]
    engine.create_mesh("dup", verts, faces)
    before_count = engine.snapshot("dup").vertex_count
    assert find_loose_or_duplicate(engine, "dup") != ()

    outcome = weld_duplicates(engine, "dup")

    assert outcome.fixed >= 1
    assert engine.snapshot("dup").vertex_count < before_count
    assert find_loose_or_duplicate(engine, "dup") == ()


# ----------------------------------------------------------------------- remove_loose

def test_remove_loose_deletes_a_vertex_referenced_by_no_face(engine) -> None:
    verts, faces = unit_cube()
    verts = list(verts) + [Vec3(9, 9, 9)]  # referenced by no face
    engine.create_mesh("loose", verts, faces)
    before_count = engine.snapshot("loose").vertex_count
    assert find_loose_or_duplicate(engine, "loose") != ()

    outcome = remove_loose(engine, "loose")

    assert outcome.fixed == 1
    assert engine.snapshot("loose").vertex_count == before_count - 1
    assert find_loose_or_duplicate(engine, "loose") == ()


# ------------------------------------------------------------------------ fix_normals

def test_fix_normals_corrects_a_single_reversed_face(engine) -> None:
    verts, faces = unit_cube()
    faces = list(faces)
    faces[0] = tuple(reversed(faces[0]))
    engine.create_mesh("flipped", verts, faces)
    assert find_flipped_normals(engine, "flipped") != ()

    outcome = fix_normals(engine, "flipped")

    assert outcome.fixed == 1
    assert find_flipped_normals(engine, "flipped") == ()


# ------------------------------------------------------------------- close_visual_gap

def test_close_visual_gap_brings_two_boxes_to_touching(engine) -> None:
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(1.005, 0, 0)))
    assert gap_width(engine, "a", "b").value == pytest.approx(0.005, abs=1e-6)

    outcome = close_visual_gap(engine, "a", "b", max_gap=0.01)

    assert outcome.fixed == 1
    assert gap_width(engine, "a", "b").value == pytest.approx(0.0, abs=1e-9)


def test_close_visual_gap_skips_when_the_gap_exceeds_max_gap(engine) -> None:
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(2, 0, 0)))

    outcome = close_visual_gap(engine, "a", "b", max_gap=0.01)

    assert outcome.fixed == 0
    assert outcome.skipped == 1
    assert outcome.reason != ""


# ------------------------------------------------------------------------ merge_shells

def test_merge_shells_welds_two_nearby_shells(engine) -> None:
    verts_a, faces_a = unit_cube(Vec3(1, 1, 1))
    verts_b, faces_b = unit_cube(Vec3(1, 1, 1))
    shifted_b = [v + Vec3(1.0005, 0, 0) for v in verts_b]
    verts = list(verts_a) + shifted_b
    faces = list(faces_a) + [tuple(i + 8 for i in f) for f in faces_b]
    engine.create_mesh("shells", verts, faces)
    before_count = engine.snapshot("shells").vertex_count

    outcome = merge_shells(engine, "shells", max_distance=0.001)

    assert outcome.fixed >= 1
    assert engine.snapshot("shells").vertex_count < before_count


# ------------------------------------------------------------------ split_non_manifold

def test_split_non_manifold_reports_rather_than_claims_a_false_fix(engine) -> None:
    """No ``EngineProtocol`` primitive can split a fan or duplicate a pinch vertex
    (``CLAUDE.md``) — this must say so honestly, never report ``fixed`` while the defect
    is still measurable."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(-1, 0, 0), Vec3(0, -1, 0)]
    faces = [(0, 1, 2), (0, 3, 4)]
    engine.create_mesh("pinch", verts, faces)

    outcome = split_non_manifold(engine, "pinch")

    assert outcome.fixed == 0
    assert outcome.skipped >= 1
    assert outcome.reason != ""
    assert find_non_manifold_vertices(engine, "pinch") != ()


# ----------------------------------------------------------------------------- repair

def test_repair_on_a_clean_mesh_changes_nothing(engine) -> None:
    """A repair pass that "fixes" a healthy mesh is worse than none."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    before = engine.snapshot("box")

    outcomes = repair(engine, "box")

    assert outcomes != ()
    assert all(o == RepairOutcome() for o in outcomes)
    assert engine.snapshot("box") == before


def test_repair_re_measures_between_tiers_rather_than_trusting_a_primitive(engine) -> None:
    """``weld_duplicates`` welding the duplicate does not, by itself, make the detector go
    quiet — a genuinely loose vertex is still present and must still show as skipped for
    that tier, not silently folded into "fixed" because a mutating call was made."""
    verts, faces = unit_cube()
    verts = list(verts) + [verts[0], Vec3(9, 9, 9)]  # 8: duplicates 0; 9: loose
    faces = list(faces) + [(8, 1, 4)]  # reference vertex 8 so it reads as duplicate, not loose
    engine.create_mesh("messy", verts, faces)

    weld_outcome, remove_outcome = repair(
        engine, "messy", classes=(DefectClass.LOOSE_OR_DUPLICATE,)
    )

    assert weld_outcome.fixed == 1 and weld_outcome.skipped == 1
    assert remove_outcome.fixed == 1 and remove_outcome.skipped == 0
    assert find_loose_or_duplicate(engine, "messy") == ()


def test_repair_classes_filter_limits_which_tiers_run(engine) -> None:
    verts, faces = unit_cube()
    engine.create_mesh("open_only", verts, faces[:-1])

    outcomes = repair(engine, "open_only", classes=(DefectClass.BOUNDARY_HOLE,))

    assert len(outcomes) == 1
    assert outcomes[0].fixed == 1
    assert find_boundary_holes(engine, "open_only") == ()


def test_repair_is_idempotent(engine) -> None:
    verts, faces = unit_cube()
    engine.create_mesh("fixable", verts, faces[:-1])

    repair(engine, "fixable")
    after_first = engine.snapshot("fixable")
    second_outcomes = repair(engine, "fixable")
    after_second = engine.snapshot("fixable")

    assert after_first == after_second
    assert all(o == RepairOutcome() for o in second_outcomes)


# ------------------------------------------------------------------------- GAPS_SPECS

def test_gaps_specs_are_all_mutating_and_never_exposed_to_inspect() -> None:
    """Many INSPECT agents run concurrently precisely because none of their tools can
    mutate (ADR-007) — every repair in this package mutates. ``ToolSpec.__post_init__``
    would already have raised at import if any entry got this wrong."""
    assert GAPS_SPECS
    assert all(spec.mutating for spec in GAPS_SPECS)
    assert all(ToolRole.INSPECT not in spec.roles for spec in GAPS_SPECS)
