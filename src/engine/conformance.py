"""The conformance suite: one behavioural check per function, run against both engines.

``FakeEngine`` is the specification (``src/testing/fake_engine.py``): every module outside
``src/engine/`` is tested against it, so if ``BlenderEngine`` disagrees with it on any of
these checks, every one of those modules' suites is testing a lie. ``src/engine/
conformance_test.py`` runs universal + fake-only checks against ``FakeEngine`` — it should
never go red, because ``FakeEngine`` is frozen, main-agent-owned infrastructure this module
does not write. ``src/engine/blender_test.py`` runs universal + Blender-only checks against
the real ``BlenderEngine``; failing there (starting with ``NotImplementedError``, per Rule 4
RED) is expected until the engine is implemented.

The individual checks live one file per actor, mirroring the stub split in this same
directory (``mesh.py``, ``modifiers.py``, ``surfacing.py``, ``exporting.py``, ``raw.py``,
``session.py``), plus four added by a conformance audit for concerns with no actor file of
their own: ``conformance_mesh.py``, ``conformance_modifiers.py``, ``conformance_boolean.py``,
``conformance_shape.py``, ``conformance_surfacing.py``, ``conformance_materials.py``,
``conformance_exporting.py``, ``conformance_raw.py``, ``conformance_session.py``,
``conformance_validation.py``. This file is the barrel — it re-exports every check plus the
three registries below.

**Three registries, not two.** The original design had only universal and Blender-only. A
conformance audit added a genuine third case: a handful of checks are the only way to pin
down real behaviour (a solver argument that cannot show a geometric difference on a trivial
input; a guaranteed-unavailable capability) but can *only* run against ``FakeEngine``,
because they depend on ``FakeEngine``-only introspection (``engine.calls``, the test-only
``.material()`` accessor) or a fixture (``engine_without_bake``) with no real-engine
equivalent at all.

- ``UNIVERSAL_CHECKS`` — hold for any conforming ``EngineProtocol``. Both test files call
  these.
- ``BLENDER_ONLY_CHECKS`` — only a real ``bpy`` backend can meaningfully satisfy them.
  Called only from ``blender_test.py``.
- ``FAKE_ONLY_CHECKS`` — only ``FakeEngine`` (or its special ``engine_without_bake``
  fixture) can meaningfully satisfy them. Called only from ``conformance_test.py``.

Why each Blender-only or fake-only check is exempt from the other side is documented at its
own definition, not repeated here. Two recurring reasons worth naming up front because they
explain most of the list:

- ``FakeEngine`` exists "to exercise placement, measurement and bookkeeping" (its own
  docstring) — not to reproduce Blender's tessellation, real CSG, real UV projection, or a
  real filesystem. Checks that need any of those are Blender-only.
- ``FakeEngine.calls`` and its test-only accessors (e.g. ``.material()``) are not part of
  ``EngineProtocol`` and have no real-engine equivalent. Checks whose only observable signal
  is one of these are fake-only; ``conformance_boolean.check_boolean_solver_choice_is_
  threaded_through`` and ``conformance_materials.check_set_pbr_updates_roughness_
  observably`` explain, at their own definitions, why introspecting the real engine instead
  would mean depending on Blender's node-socket names, which ADR-001 documents as breaking
  between versions with no deprecation policy — exactly the fragility this suite avoids
  everywhere else.

Two of the original checks deliberately do **not** copy a ``fake_engine_test.py`` assertion
verbatim, because that exact assertion is a ``FakeEngine`` implementation detail rather than
part of ``EngineProtocol``'s contract — see each check's own docstring in
``conformance_surfacing.py`` for ``check_unwrap_produces_uvs_in_unit_range`` (Blender stores
UVs per face-corner, not per vertex) and ``check_bake_requires_unwrap_first`` (an explicit
validation-order requirement).
"""

from __future__ import annotations

from .conformance_boolean import (
    check_boolean_difference_bounds_stay_within_the_original_target,
    check_boolean_difference_removes_the_cutter,
    check_boolean_intersect_matches_the_geometric_overlap_bounds,
    check_boolean_intersect_removes_the_cutter,
    check_boolean_solver_choice_is_threaded_through,
)
from .conformance_exporting import (
    check_export_gltf_threads_the_full_conversion_through,
    check_export_gltf_writes_a_nonempty_file,
)
from .conformance_materials import (
    check_create_material_and_assign_material_reach_the_snapshot,
    check_set_pbr_updates_roughness_observably,
)
from .conformance_mesh import (
    check_snapshot_triangulates_a_quad_mesh,
    check_apply_transform_bakes_scale_into_vertices,
    check_create_mesh_produces_a_closed_manifold,
    check_create_primitive_returns_the_actual_assigned_id,
    check_delete_removes_exactly_the_named_object,
    check_duplicate_produces_an_independent_copy,
    check_join_brings_source_vertices_into_the_targets_local_space,
    check_primitive_has_expected_world_bounds,
    check_unknown_object_error_names_what_exists,
)
from .conformance_modifiers import (
    check_array_along_curve_keeps_instances_plumb_on_a_slope,
    check_array_along_curve_tilts_when_upright_is_disabled,
    check_array_includes_forced_corner_positions,
    check_array_uses_the_caller_supplied_name_template,
    check_bevel_edges_moves_only_the_selected_edges_geometry,
    check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged,
    check_bevel_edges_with_explicit_selection_increases_triangle_count,
    check_bevel_refuses_unapplied_scale,
    check_boolean_union_matches_bounds_and_removes_cutter,
    check_fill_holes_closes_an_open_box,
    check_fill_holes_reports_what_it_could_not_do,
    check_merge_by_distance_welds_coincident_vertices,
    check_separate_loose_splits_disconnected_shells,
)
from .conformance_raw import (
    check_execute_propagates_a_raising_source,
    check_execute_runs_against_live_context,
)
from .conformance_session import (
    check_backend_name_identifies_bpy,
    check_reset_clears_the_live_bpy_scene,
    check_reset_leaves_zero_objects,
)
from .conformance_shape import (
    check_decimate_reduces_the_polygon_count,
    check_recalculate_normals_inside_flips_the_winding,
    check_solidify_thickens_by_the_requested_amount,
)
from .conformance_surfacing import (
    check_bake_raises_engine_unavailable_when_capability_is_absent,
    check_bake_requires_unwrap_first,
    check_bake_succeeds_or_raises_capability_error,
    check_mark_seams_changes_the_subsequent_unwrap,
    check_unwrap_produces_uvs_in_unit_range,
)
from .conformance_validation import (
    check_array_along_curve_rejects_a_curve_with_fewer_than_two_points,
    check_array_along_curve_rejects_non_positive_spacing,
    check_boolean_rejects_an_unknown_mode,
    check_boolean_rejects_an_unknown_solver,
    check_create_mesh_rejects_an_empty_vertex_list,
    check_create_primitive_rejects_an_unknown_kind,
    check_decimate_rejects_a_ratio_outside_the_unit_interval,
    check_export_gltf_rejects_an_empty_object_list,
    check_export_gltf_rejects_non_positive_scale,
    check_set_pbr_rejects_an_unknown_material,
    check_solidify_rejects_non_positive_thickness,
)

#: Every check that holds for any conforming ``EngineProtocol``. Both test files call these.
UNIVERSAL_CHECKS = (
    check_snapshot_triangulates_a_quad_mesh,
    check_primitive_has_expected_world_bounds,
    check_create_mesh_produces_a_closed_manifold,
    check_create_primitive_returns_the_actual_assigned_id,
    check_apply_transform_bakes_scale_into_vertices,
    check_unknown_object_error_names_what_exists,
    check_duplicate_produces_an_independent_copy,
    check_delete_removes_exactly_the_named_object,
    check_join_brings_source_vertices_into_the_targets_local_space,
    check_reset_leaves_zero_objects,
    check_bevel_refuses_unapplied_scale,
    check_bevel_edges_with_explicit_selection_increases_triangle_count,
    check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged,
    check_boolean_union_matches_bounds_and_removes_cutter,
    check_boolean_difference_removes_the_cutter,
    check_boolean_intersect_removes_the_cutter,
    check_array_along_curve_keeps_instances_plumb_on_a_slope,
    check_array_along_curve_tilts_when_upright_is_disabled,
    check_array_includes_forced_corner_positions,
    check_array_uses_the_caller_supplied_name_template,
    check_merge_by_distance_welds_coincident_vertices,
    check_fill_holes_closes_an_open_box,
    check_fill_holes_reports_what_it_could_not_do,
    check_separate_loose_splits_disconnected_shells,
    check_solidify_thickens_by_the_requested_amount,
    check_decimate_reduces_the_polygon_count,
    check_recalculate_normals_inside_flips_the_winding,
    check_unwrap_produces_uvs_in_unit_range,
    check_bake_requires_unwrap_first,
    check_bake_succeeds_or_raises_capability_error,
    check_create_material_and_assign_material_reach_the_snapshot,
    check_export_gltf_threads_the_full_conversion_through,
    check_execute_runs_against_live_context,
    check_execute_propagates_a_raising_source,
    check_create_mesh_rejects_an_empty_vertex_list,
    check_create_primitive_rejects_an_unknown_kind,
    check_boolean_rejects_an_unknown_mode,
    check_boolean_rejects_an_unknown_solver,
    check_solidify_rejects_non_positive_thickness,
    check_array_along_curve_rejects_non_positive_spacing,
    check_array_along_curve_rejects_a_curve_with_fewer_than_two_points,
    check_decimate_rejects_a_ratio_outside_the_unit_interval,
    check_export_gltf_rejects_an_empty_object_list,
    check_export_gltf_rejects_non_positive_scale,
    check_set_pbr_rejects_an_unknown_material,
)

#: Checks that only a real ``bpy`` backend can meaningfully satisfy — see the module
#: docstring, and each check's own definition, for why ``FakeEngine`` is exempt. Only
#: ``blender_test.py`` calls these.
BLENDER_ONLY_CHECKS = (
    check_backend_name_identifies_bpy,
    check_export_gltf_writes_a_nonempty_file,
    check_reset_clears_the_live_bpy_scene,
    check_mark_seams_changes_the_subsequent_unwrap,
    check_boolean_difference_bounds_stay_within_the_original_target,
    check_boolean_intersect_matches_the_geometric_overlap_bounds,
    check_bevel_edges_moves_only_the_selected_edges_geometry,
)

#: Checks that only ``FakeEngine`` (or its ``engine_without_bake`` fixture) can meaningfully
#: satisfy — see the module docstring, and each check's own definition, for why. Only
#: ``conformance_test.py`` calls these.
FAKE_ONLY_CHECKS = (
    check_boolean_solver_choice_is_threaded_through,
    check_set_pbr_updates_roughness_observably,
    check_bake_raises_engine_unavailable_when_capability_is_absent,
)

__all__ = [
    "UNIVERSAL_CHECKS",
    "BLENDER_ONLY_CHECKS",
    "FAKE_ONLY_CHECKS",
    *(fn.__name__ for fn in UNIVERSAL_CHECKS),
    *(fn.__name__ for fn in BLENDER_ONLY_CHECKS),
    *(fn.__name__ for fn in FAKE_ONLY_CHECKS),
]
