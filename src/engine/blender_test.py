"""Runs every conformance check — universal and Blender-only — against the real ``bpy``.

Every test in this file is ``@pytest.mark.needs_blender`` (applied once, at module level,
via ``pytestmark``, so no individual test can forget it). The root ``conftest.py`` skips
them automatically when ``bpy`` is not importable, which is why this module must import
cleanly on a machine with no Blender at all: ``engine.BlenderEngine`` and
``engine.conformance`` import no bpy themselves at this stage (Rule 4 RED — the stubs raise,
they do not import), so collection never fails with ``ImportError`` even when every test
inside ends up skipped.

At RED, before an implementer exists, every test here fails with ``NotImplementedError`` —
raised from the ``engine`` fixture's own ``reset()`` call, since every ``BlenderEngine``
method currently raises. That is the expected, correct failure mode (never ``ImportError``).

The ``engine`` fixture resets before *and* after each test. A shared bpy session is global
mutable state (unlike ``FakeEngine``, which conftest.py hands out fresh per test) — without
resetting on both sides, one test's leftover objects could make the next test pass or fail
for the wrong reason.
"""

from __future__ import annotations

import pytest

from contracts import EngineProtocol

from engine import BlenderEngine, conformance, create_engine

pytestmark = pytest.mark.needs_blender


@pytest.fixture
def engine():
    eng = BlenderEngine()
    eng.reset()
    yield eng
    eng.reset()


def test_primitive_has_expected_world_bounds(engine) -> None:
    """If wrong: every generated primitive is the wrong physical size."""
    conformance.check_primitive_has_expected_world_bounds(engine)


def test_create_mesh_produces_a_closed_manifold(engine) -> None:
    """If wrong: manifold checks downstream of mesh creation (boolean, solidify, export)
    are meaningless because the base geometry already leaks."""
    conformance.check_create_mesh_produces_a_closed_manifold(engine)


def test_create_primitive_returns_the_actual_assigned_id(engine) -> None:
    """If wrong: a caller writes to the wrong object, or to nothing, after bpy renamed it
    on a name collision."""
    conformance.check_create_primitive_returns_the_actual_assigned_id(engine)


def test_apply_transform_bakes_scale_into_vertices(engine) -> None:
    """If wrong: unapplied scale silently corrupts every later bevel, boolean and physics
    result while looking correct in a viewport."""
    conformance.check_apply_transform_bakes_scale_into_vertices(engine)


def test_unknown_object_error_names_what_exists(engine) -> None:
    """If wrong: an agent that mistypes an id gets no way to self-correct."""
    conformance.check_unknown_object_error_names_what_exists(engine)


def test_reset_leaves_zero_objects(engine) -> None:
    """The naive-implementation catcher: a fresh bpy scene holds the default cube, camera
    and light. If reset() only forgets objects it tracked itself, this fails."""
    conformance.check_reset_leaves_zero_objects(engine)


def test_bevel_refuses_unapplied_scale(engine) -> None:
    """If wrong: a bevel silently produces uneven width that is invisible until measured."""
    conformance.check_bevel_refuses_unapplied_scale(engine)


def test_bevel_edges_with_explicit_selection_increases_triangle_count(engine) -> None:
    """If wrong: bevel_edges is either a no-op or bevels the wrong (or every) edge, and a
    detail pass's "which edges plausibly catch light" heuristic stops mattering."""
    conformance.check_bevel_edges_with_explicit_selection_increases_triangle_count(engine)


def test_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged(engine) -> None:
    """If wrong: bevel_edges ignores edge_indices and bevels everything regardless,
    which the previous test alone cannot detect."""
    conformance.check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged(engine)


def test_boolean_union_matches_bounds_and_removes_cutter(engine) -> None:
    """If wrong: a union drops geometry silently, or the cutter lingers as an orphaned
    duplicate that renders twice and double-counts in a polygon budget."""
    conformance.check_boolean_union_matches_bounds_and_removes_cutter(engine)


def test_array_along_curve_keeps_instances_plumb_on_a_slope(engine) -> None:
    """The single most important behavioural test in the product: posts on a stair rake
    must stay plumb, not lean at the stair angle — the classic naive-generator failure this
    tool exists to prevent."""
    conformance.check_array_along_curve_keeps_instances_plumb_on_a_slope(engine)


def test_array_along_curve_tilts_when_upright_is_disabled(engine) -> None:
    """If wrong: the plumb test above could pass even with keep_upright silently ignored,
    because the "wrong" behaviour would never be reachable to compare against."""
    conformance.check_array_along_curve_tilts_when_upright_is_disabled(engine)


def test_array_includes_forced_corner_positions(engine) -> None:
    """If wrong: a railing corner gets a gap or a doubled baluster."""
    conformance.check_array_includes_forced_corner_positions(engine)


def test_array_uses_the_caller_supplied_name_template(engine) -> None:
    """If wrong: instance ids are unpredictable before the call, so per-instance
    constraints (e.g. one ConstraintSet per baluster) cannot be pre-declared."""
    conformance.check_array_uses_the_caller_supplied_name_template(engine)


def test_merge_by_distance_welds_coincident_vertices(engine) -> None:
    """If wrong: unwelded duplicate vertices break every operation downstream that assumes
    a shared edge, invisibly."""
    conformance.check_merge_by_distance_welds_coincident_vertices(engine)


def test_fill_holes_closes_an_open_box(engine) -> None:
    """If wrong: an unfilled hole ships in the final asset — light leaks through a wall, or
    a game engine's collision mesh has a gap a player falls through."""
    conformance.check_fill_holes_closes_an_open_box(engine)


def test_fill_holes_reports_what_it_could_not_do(engine) -> None:
    """If wrong: a caller cannot tell "nothing to do" from "found a hole and refused it",
    both zero, and reports a clean mesh that still has a hole."""
    conformance.check_fill_holes_reports_what_it_could_not_do(engine)


def test_separate_loose_splits_disconnected_shells(engine) -> None:
    """If wrong: two disconnected shells stay one object, so a per-object operation on one
    silently also hits the other."""
    conformance.check_separate_loose_splits_disconnected_shells(engine)


def test_unwrap_produces_uvs_in_unit_range(engine) -> None:
    """If wrong: a UV outside [0, 1] wraps or clamps unpredictably at bake/export time,
    producing a visibly wrong texture with no error anywhere."""
    conformance.check_unwrap_produces_uvs_in_unit_range(engine)


def test_bake_requires_unwrap_first(engine) -> None:
    """If wrong: a caller who forgot to unwrap gets an unrelated error instead of the
    actionable "call unwrap() first"."""
    conformance.check_bake_requires_unwrap_first(engine)


def test_bake_succeeds_or_raises_capability_error(engine, tmp_path) -> None:
    """If wrong: in-process bpy's missing windowed context (ADR-001) surfaces as a bare,
    unparseable exception instead of a named EngineUnavailable an agent can act on."""
    conformance.check_bake_succeeds_or_raises_capability_error(engine, tmp_path)


def test_execute_runs_against_live_context(engine) -> None:
    """If wrong: execute() runs against a private copy of the scene — it looks like it ran,
    but nothing a later call observes actually changed."""
    conformance.check_execute_runs_against_live_context(engine)


def test_execute_propagates_a_raising_source(engine) -> None:
    """If wrong: execute() swallows or rewraps the caller's exception, breaking every call
    site's own wrapper, which expects the original exception as __cause__."""
    conformance.check_execute_propagates_a_raising_source(engine)


def test_backend_name_identifies_bpy(engine) -> None:
    """If wrong: a scene document cannot say which engine produced a result, so a
    discrepancy after a Blender version bump (ADR-001) is unexplainable after the fact."""
    conformance.check_backend_name_identifies_bpy(engine)


def test_export_gltf_writes_a_nonempty_file(engine, tmp_path) -> None:
    """If wrong: export_gltf reports success while the exported asset does not exist on
    disk, and the caller has no way to know until something downstream tries to load it."""
    conformance.check_export_gltf_writes_a_nonempty_file(engine, tmp_path)


def test_create_engine_returns_a_conforming_backend() -> None:
    """create_engine() is the one seam the rest of the product is allowed to depend on
    (ADR-008's composition root). If it returns something that does not structurally satisfy
    EngineProtocol, or whose backend_name does not identify bpy, every caller downstream of
    the factory is silently talking to the wrong thing."""
    eng = create_engine()
    assert isinstance(eng, EngineProtocol)
    assert eng.backend_name.startswith("bpy-")


# ---------------------------------------------------------- added by a conformance audit

def test_duplicate_produces_an_independent_copy(engine) -> None:
    """If wrong: moving a duplicated object also moves the source it was copied from."""
    conformance.check_duplicate_produces_an_independent_copy(engine)


def test_delete_removes_exactly_the_named_object(engine) -> None:
    """If wrong: delete removes the wrong object, or more than one — silent data loss."""
    conformance.check_delete_removes_exactly_the_named_object(engine)


def test_join_brings_source_vertices_into_the_targets_local_space(engine) -> None:
    """If wrong: joined geometry appears offset by the source object's old transform."""
    conformance.check_join_brings_source_vertices_into_the_targets_local_space(engine)


def test_bevel_edges_moves_only_the_selected_edges_geometry(engine) -> None:
    """If wrong: bevel_edges ignores which edges were selected and always bevels a fixed
    set, enabling the blanket-bevel artificiality tell the Protocol docstring warns about."""
    conformance.check_bevel_edges_moves_only_the_selected_edges_geometry(engine)


def test_boolean_difference_removes_the_cutter(engine) -> None:
    """If wrong: the cutter lingers after a difference and renders a second time."""
    conformance.check_boolean_difference_removes_the_cutter(engine)


def test_boolean_intersect_removes_the_cutter(engine) -> None:
    """If wrong: the cutter lingers after an intersect and renders a second time."""
    conformance.check_boolean_intersect_removes_the_cutter(engine)


def test_solidify_thickens_by_the_requested_amount(engine) -> None:
    """If wrong: a no-op or wrongly-scaled solidify ships a wall with no real thickness."""
    conformance.check_solidify_thickens_by_the_requested_amount(engine)


def test_decimate_reduces_the_polygon_count(engine) -> None:
    """If wrong: a LOD request silently produces no LOD at all."""
    conformance.check_decimate_reduces_the_polygon_count(engine)


def test_recalculate_normals_inside_flips_the_winding(engine) -> None:
    """If wrong: recalculate_normals(inside=True) is a no-op and produces no way to
    deliberately generate inside-out geometry, with the render coming back wrong."""
    conformance.check_recalculate_normals_inside_flips_the_winding(engine)


def test_create_material_and_assign_material_reach_the_snapshot(engine) -> None:
    """If wrong: an assigned material never reaches the object; the export ships bare."""
    conformance.check_create_material_and_assign_material_reach_the_snapshot(engine)


def test_export_gltf_threads_the_full_conversion_through(engine, tmp_path) -> None:
    """If wrong: mirror_x/negate_rotation/scale are silently dropped before reaching the
    exporter — the exact round-trip mirroring bug those parameters exist to prevent."""
    conformance.check_export_gltf_threads_the_full_conversion_through(engine, tmp_path)


def test_create_mesh_rejects_an_empty_vertex_list(engine) -> None:
    """If wrong: a zero-vertex mesh is silently accepted and crashes something downstream,
    far from where the bad input was actually supplied."""
    conformance.check_create_mesh_rejects_an_empty_vertex_list(engine)


def test_create_primitive_rejects_an_unknown_kind(engine) -> None:
    """If wrong: a typo'd primitive kind is silently accepted instead of rejected."""
    conformance.check_create_primitive_rejects_an_unknown_kind(engine)


def test_boolean_rejects_an_unknown_mode(engine) -> None:
    """If wrong: an invalid boolean mode is silently coerced to a default the caller never
    asked for."""
    conformance.check_boolean_rejects_an_unknown_mode(engine)


def test_boolean_rejects_an_unknown_solver(engine) -> None:
    """If wrong: an invalid solver is silently coerced, hiding the choice a caller made to
    avoid a known solver bug."""
    conformance.check_boolean_rejects_an_unknown_solver(engine)


def test_solidify_rejects_non_positive_thickness(engine) -> None:
    """If wrong: a zero/negative thickness silently produces a degenerate shell."""
    conformance.check_solidify_rejects_non_positive_thickness(engine)


def test_array_along_curve_rejects_non_positive_spacing(engine) -> None:
    """If wrong: zero spacing hangs or silently produces one instance instead of erroring."""
    conformance.check_array_along_curve_rejects_non_positive_spacing(engine)


def test_array_along_curve_rejects_a_curve_with_fewer_than_two_points(engine) -> None:
    """If wrong: a single-point "curve" silently places one instance instead of erroring."""
    conformance.check_array_along_curve_rejects_a_curve_with_fewer_than_two_points(engine)


def test_decimate_rejects_a_ratio_outside_the_unit_interval(engine) -> None:
    """If wrong: an out-of-range ratio is silently clamped instead of rejected."""
    conformance.check_decimate_rejects_a_ratio_outside_the_unit_interval(engine)


def test_export_gltf_rejects_an_empty_object_list(engine, tmp_path) -> None:
    """If wrong: an export with nothing selected silently reports success."""
    conformance.check_export_gltf_rejects_an_empty_object_list(engine, tmp_path)


def test_export_gltf_rejects_non_positive_scale(engine, tmp_path) -> None:
    """If wrong: a zero/negative scale silently collapses or inverts the exported asset."""
    conformance.check_export_gltf_rejects_non_positive_scale(engine, tmp_path)


def test_set_pbr_rejects_an_unknown_material(engine) -> None:
    """If wrong: writing PBR values to a nonexistent material silently does nothing."""
    conformance.check_set_pbr_rejects_an_unknown_material(engine)


def test_reset_clears_the_live_bpy_scene(engine) -> None:
    """The naive-implementation catcher, direct-bpy edition: if list_objects() reads a
    private Python-side ledger instead of bpy.data, reset() can clear that ledger and never
    touch the live scene at all — every other check in this suite would still pass while
    objects sit in bpy.data forever."""
    conformance.check_reset_clears_the_live_bpy_scene(engine)


def test_mark_seams_changes_the_subsequent_unwrap(engine) -> None:
    """If wrong: a no-op mark_seams passes every other UV check, and the UV layout is wrong
    for anything but the trivial default projection, with no error anywhere to catch it."""
    conformance.check_mark_seams_changes_the_subsequent_unwrap(engine)


def test_boolean_difference_bounds_stay_within_the_original_target(engine) -> None:
    """If wrong: a difference operation grows the target instead of only ever cutting
    material away from it — a real CSG solver must never do this."""
    conformance.check_boolean_difference_bounds_stay_within_the_original_target(engine)


def test_boolean_intersect_matches_the_geometric_overlap_bounds(engine) -> None:
    """If wrong: intersect does not actually shrink to the geometric overlap of the two
    inputs — the defining property of the operation."""
    conformance.check_boolean_intersect_matches_the_geometric_overlap_bounds(engine)
