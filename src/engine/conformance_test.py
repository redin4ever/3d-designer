"""Runs every universal + fake-only conformance check against ``FakeEngine``.

No ``needs_blender`` marker: this file always runs, on any machine, with no Blender
installed. It is the "control" side of the conformance suite (``src/engine/
blender_test.py`` is the other side, against the real backend) — since ``FakeEngine`` is the
specification these checks are drawn from, this file should never fail. If it does, either
``FakeEngine`` regressed (main-agent-owned, so check ``src/testing/`` was not accidentally
touched) or a check's own assumption about the shared contract is wrong.

Uses the root ``engine`` fixture from ``conftest.py`` — a fresh ``FakeEngine()`` per test —
rather than defining its own, so it cannot drift from what every other module's suite uses.
The three fake-only checks at the bottom of this file (``conformance.FAKE_ONLY_CHECKS``) run
only here, never from ``blender_test.py`` — see ``conformance.py``'s module docstring for
why each depends on something only ``FakeEngine`` has.
"""

from __future__ import annotations

from testing import FakeEngine

from engine import conformance


def test_primitive_has_expected_world_bounds(engine: FakeEngine) -> None:
    """If wrong: every generated primitive is the wrong physical size."""
    conformance.check_primitive_has_expected_world_bounds(engine)


def test_create_mesh_produces_a_closed_manifold(engine: FakeEngine) -> None:
    """If wrong: manifold checks downstream of mesh creation (boolean, solidify, export)
    are meaningless because the base geometry already leaks."""
    conformance.check_create_mesh_produces_a_closed_manifold(engine)


def test_create_primitive_returns_the_actual_assigned_id(engine: FakeEngine) -> None:
    """If wrong: a caller writes to the wrong object, or to nothing, after a name collision
    the engine silently resolved by renaming."""
    conformance.check_create_primitive_returns_the_actual_assigned_id(engine)


def test_apply_transform_bakes_scale_into_vertices(engine: FakeEngine) -> None:
    """If wrong: unapplied scale silently corrupts every later bevel, boolean and physics
    result while looking correct in a viewport."""
    conformance.check_apply_transform_bakes_scale_into_vertices(engine)


def test_unknown_object_error_names_what_exists(engine: FakeEngine) -> None:
    """If wrong: an agent that mistypes an id gets no way to self-correct."""
    conformance.check_unknown_object_error_names_what_exists(engine)


def test_reset_leaves_zero_objects(engine: FakeEngine) -> None:
    """If wrong: every "the scene starts empty" assumption in the product is false on the
    very first operation of a run."""
    conformance.check_reset_leaves_zero_objects(engine)


def test_bevel_refuses_unapplied_scale(engine: FakeEngine) -> None:
    """If wrong: a bevel silently produces uneven width that is invisible until measured."""
    conformance.check_bevel_refuses_unapplied_scale(engine)


def test_bevel_edges_with_explicit_selection_increases_triangle_count(engine: FakeEngine) -> None:
    """If wrong: bevel_edges is either a no-op or bevels the wrong (or every) edge, and a
    detail pass's "which edges plausibly catch light" heuristic stops mattering."""
    conformance.check_bevel_edges_with_explicit_selection_increases_triangle_count(engine)


def test_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged(
    engine: FakeEngine,
) -> None:
    """If wrong: bevel_edges ignores edge_indices and bevels everything regardless,
    which the previous test alone cannot detect."""
    conformance.check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged(engine)


def test_boolean_union_matches_bounds_and_removes_cutter(engine: FakeEngine) -> None:
    """If wrong: a union drops geometry silently, or the cutter lingers as an orphaned
    duplicate that renders twice and double-counts in a polygon budget."""
    conformance.check_boolean_union_matches_bounds_and_removes_cutter(engine)


def test_array_along_curve_keeps_instances_plumb_on_a_slope(engine: FakeEngine) -> None:
    """The single most important behavioural test in the product: posts on a stair rake
    must stay plumb, not lean at the stair angle — the classic naive-generator failure."""
    conformance.check_array_along_curve_keeps_instances_plumb_on_a_slope(engine)


def test_array_along_curve_tilts_when_upright_is_disabled(engine: FakeEngine) -> None:
    """If wrong: the plumb test above could pass even with keep_upright silently ignored,
    because the "wrong" behaviour would never be reachable to compare against."""
    conformance.check_array_along_curve_tilts_when_upright_is_disabled(engine)


def test_array_includes_forced_corner_positions(engine: FakeEngine) -> None:
    """If wrong: a railing corner gets a gap or a doubled baluster."""
    conformance.check_array_includes_forced_corner_positions(engine)


def test_array_uses_the_caller_supplied_name_template(engine: FakeEngine) -> None:
    """If wrong: instance ids are unpredictable before the call, so per-instance
    constraints (e.g. one ConstraintSet per baluster) cannot be pre-declared."""
    conformance.check_array_uses_the_caller_supplied_name_template(engine)


def test_merge_by_distance_welds_coincident_vertices(engine: FakeEngine) -> None:
    """If wrong: unwelded duplicate vertices break every operation downstream that assumes
    a shared edge, invisibly."""
    conformance.check_merge_by_distance_welds_coincident_vertices(engine)


def test_fill_holes_closes_an_open_box(engine: FakeEngine) -> None:
    """If wrong: an unfilled hole ships in the final asset — light leaks through a wall, or
    a game engine's collision mesh has a gap a player falls through."""
    conformance.check_fill_holes_closes_an_open_box(engine)


def test_fill_holes_reports_what_it_could_not_do(engine: FakeEngine) -> None:
    """If wrong: a caller cannot tell "nothing to do" from "found a hole and refused it",
    both zero, and reports a clean mesh that still has a hole."""
    conformance.check_fill_holes_reports_what_it_could_not_do(engine)


def test_separate_loose_splits_disconnected_shells(engine: FakeEngine) -> None:
    """If wrong: two disconnected shells stay one object, so a per-object operation on one
    silently also hits the other."""
    conformance.check_separate_loose_splits_disconnected_shells(engine)


def test_unwrap_produces_uvs_in_unit_range(engine: FakeEngine) -> None:
    """If wrong: a UV outside [0, 1] wraps or clamps unpredictably at bake/export time,
    producing a visibly wrong texture with no error anywhere."""
    conformance.check_unwrap_produces_uvs_in_unit_range(engine)


def test_bake_requires_unwrap_first(engine: FakeEngine) -> None:
    """If wrong: a caller who forgot to unwrap gets an unrelated error instead of the
    actionable "call unwrap() first"."""
    conformance.check_bake_requires_unwrap_first(engine)


def test_bake_succeeds_or_raises_capability_error(engine: FakeEngine, tmp_path) -> None:
    """If wrong: a capability limitation (no windowed context) surfaces as a bare,
    unparseable exception instead of a named EngineUnavailable an agent can act on."""
    conformance.check_bake_succeeds_or_raises_capability_error(engine, tmp_path)


def test_execute_runs_against_live_context(engine: FakeEngine) -> None:
    """If wrong: execute() runs against a private copy of the scene — it looks like it ran,
    but nothing a later call observes actually changed."""
    conformance.check_execute_runs_against_live_context(engine)


def test_execute_propagates_a_raising_source(engine: FakeEngine) -> None:
    """If wrong: execute() swallows or rewraps the caller's exception, breaking every call
    site's own wrapper, which expects the original exception as __cause__."""
    conformance.check_execute_propagates_a_raising_source(engine)


# ---------------------------------------------------------- added by a conformance audit

def test_duplicate_produces_an_independent_copy(engine: FakeEngine) -> None:
    """If wrong: moving a duplicated object also moves the source it was copied from."""
    conformance.check_duplicate_produces_an_independent_copy(engine)


def test_delete_removes_exactly_the_named_object(engine: FakeEngine) -> None:
    """If wrong: delete removes the wrong object, or more than one — silent data loss."""
    conformance.check_delete_removes_exactly_the_named_object(engine)


def test_join_brings_source_vertices_into_the_targets_local_space(engine: FakeEngine) -> None:
    """If wrong: joined geometry appears offset by the source object's old transform."""
    conformance.check_join_brings_source_vertices_into_the_targets_local_space(engine)


def test_boolean_difference_removes_the_cutter(engine: FakeEngine) -> None:
    """If wrong: the cutter lingers after a difference and renders a second time."""
    conformance.check_boolean_difference_removes_the_cutter(engine)


def test_boolean_intersect_removes_the_cutter(engine: FakeEngine) -> None:
    """If wrong: the cutter lingers after an intersect and renders a second time."""
    conformance.check_boolean_intersect_removes_the_cutter(engine)


def test_solidify_thickens_by_the_requested_amount(engine: FakeEngine) -> None:
    """If wrong: a no-op or wrongly-scaled solidify ships a wall with no real thickness."""
    conformance.check_solidify_thickens_by_the_requested_amount(engine)


def test_decimate_reduces_the_polygon_count(engine: FakeEngine) -> None:
    """If wrong: a LOD request silently produces no LOD at all."""
    conformance.check_decimate_reduces_the_polygon_count(engine)


def test_recalculate_normals_inside_flips_the_winding(engine: FakeEngine) -> None:
    """If wrong: recalculate_normals(inside=True) is a no-op and produces no way to
    deliberately generate inside-out geometry, with the render coming back wrong."""
    conformance.check_recalculate_normals_inside_flips_the_winding(engine)


def test_create_material_and_assign_material_reach_the_snapshot(engine: FakeEngine) -> None:
    """If wrong: an assigned material never reaches the object; the export ships bare."""
    conformance.check_create_material_and_assign_material_reach_the_snapshot(engine)


def test_export_gltf_threads_the_full_conversion_through(engine: FakeEngine, tmp_path) -> None:
    """If wrong: mirror_x/negate_rotation/scale are silently dropped before reaching the
    exporter — the exact round-trip mirroring bug those parameters exist to prevent."""
    conformance.check_export_gltf_threads_the_full_conversion_through(engine, tmp_path)


def test_create_mesh_rejects_an_empty_vertex_list(engine: FakeEngine) -> None:
    """If wrong: a zero-vertex mesh is silently accepted and crashes something downstream,
    far from where the bad input was actually supplied."""
    conformance.check_create_mesh_rejects_an_empty_vertex_list(engine)


def test_create_primitive_rejects_an_unknown_kind(engine: FakeEngine) -> None:
    """If wrong: a typo'd primitive kind is silently accepted instead of rejected."""
    conformance.check_create_primitive_rejects_an_unknown_kind(engine)


def test_boolean_rejects_an_unknown_mode(engine: FakeEngine) -> None:
    """If wrong: an invalid boolean mode is silently coerced to a default the caller never
    asked for."""
    conformance.check_boolean_rejects_an_unknown_mode(engine)


def test_boolean_rejects_an_unknown_solver(engine: FakeEngine) -> None:
    """If wrong: an invalid solver is silently coerced, hiding the choice a caller made to
    avoid a known solver bug."""
    conformance.check_boolean_rejects_an_unknown_solver(engine)


def test_solidify_rejects_non_positive_thickness(engine: FakeEngine) -> None:
    """If wrong: a zero/negative thickness silently produces a degenerate shell."""
    conformance.check_solidify_rejects_non_positive_thickness(engine)


def test_array_along_curve_rejects_non_positive_spacing(engine: FakeEngine) -> None:
    """If wrong: zero spacing hangs or silently produces one instance instead of erroring."""
    conformance.check_array_along_curve_rejects_non_positive_spacing(engine)


def test_array_along_curve_rejects_a_curve_with_fewer_than_two_points(
    engine: FakeEngine,
) -> None:
    """If wrong: a single-point "curve" silently places one instance instead of erroring."""
    conformance.check_array_along_curve_rejects_a_curve_with_fewer_than_two_points(engine)


def test_decimate_rejects_a_ratio_outside_the_unit_interval(engine: FakeEngine) -> None:
    """If wrong: an out-of-range ratio is silently clamped instead of rejected."""
    conformance.check_decimate_rejects_a_ratio_outside_the_unit_interval(engine)


def test_export_gltf_rejects_an_empty_object_list(engine: FakeEngine, tmp_path) -> None:
    """If wrong: an export with nothing selected silently reports success."""
    conformance.check_export_gltf_rejects_an_empty_object_list(engine, tmp_path)


def test_export_gltf_rejects_non_positive_scale(engine: FakeEngine, tmp_path) -> None:
    """If wrong: a zero/negative scale silently collapses or inverts the exported asset."""
    conformance.check_export_gltf_rejects_non_positive_scale(engine, tmp_path)


def test_set_pbr_rejects_an_unknown_material(engine: FakeEngine) -> None:
    """If wrong: writing PBR values to a nonexistent material silently does nothing."""
    conformance.check_set_pbr_rejects_an_unknown_material(engine)


def test_boolean_solver_choice_is_threaded_through(engine: FakeEngine) -> None:
    """Fake-only (see conformance.py): the only way to catch a solver argument silently
    coerced to a fixed default, since two trivial cubes cannot show a geometric difference
    between fast/exact/manifold."""
    conformance.check_boolean_solver_choice_is_threaded_through(engine)


def test_set_pbr_updates_roughness_observably(engine: FakeEngine) -> None:
    """Fake-only (see conformance.py): no Protocol-level accessor reads PBR values back,
    so a no-op set_pbr would otherwise be invisible to this whole suite."""
    conformance.check_set_pbr_updates_roughness_observably(engine)


def test_bake_raises_engine_unavailable_when_capability_is_absent(
    engine_without_bake: FakeEngine,
) -> None:
    """Fake-only (see conformance.py): the deterministic complement to
    check_bake_succeeds_or_raises_capability_error, which is permissive because the plain
    engine fixture always supports bake. Uses the root conftest's engine_without_bake
    fixture, which simulates 'no windowed context' unconditionally."""
    conformance.check_bake_raises_engine_unavailable_when_capability_is_absent(
        engine_without_bake
    )

def test_replace_mesh_swaps_geometry_and_keeps_the_transform(engine) -> None:
    conformance.check_replace_mesh_swaps_geometry_and_keeps_the_transform(engine)


def test_replace_mesh_keeps_material_slots(engine) -> None:
    conformance.check_replace_mesh_keeps_material_slots(engine)


def test_replace_mesh_rejects_an_empty_vertex_set(engine) -> None:
    conformance.check_replace_mesh_rejects_an_empty_vertex_set(engine)

