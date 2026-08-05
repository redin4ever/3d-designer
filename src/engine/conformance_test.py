"""Runs every universal conformance check against ``FakeEngine``.

No ``needs_blender`` marker: this file always runs, on any machine, with no Blender
installed. It is the "control" side of the conformance suite (``src/engine/
blender_test.py`` is the other side, against the real backend) — since ``FakeEngine`` is the
specification these checks are drawn from, this file should never fail. If it does, either
``FakeEngine`` regressed (main-agent-owned, so check ``src/testing/`` was not accidentally
touched) or a check's own assumption about the shared contract is wrong.

Uses the root ``engine`` fixture from ``conftest.py`` — a fresh ``FakeEngine()`` per test —
rather than defining its own, so it cannot drift from what every other module's suite uses.
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
