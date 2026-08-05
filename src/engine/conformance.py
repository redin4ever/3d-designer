"""The conformance suite: one behavioural check per function, run against both engines.

``FakeEngine`` is the specification (``src/testing/fake_engine.py``): every module outside
``src/engine/`` is tested against it, so if ``BlenderEngine`` disagrees with it on any of
these checks, every one of those modules' suites is testing a lie. ``src/engine/
conformance_test.py`` runs every universal check against ``FakeEngine`` — it should never go
red, because ``FakeEngine`` is frozen, main-agent-owned infrastructure this module does not
write. ``src/engine/blender_test.py`` runs universal + Blender-only checks against the real
``BlenderEngine``; failing there (starting with ``NotImplementedError``, per Rule 4 RED) is
expected until the engine is implemented.

The individual checks live one file per actor, mirroring the stub split in this same
directory (``mesh.py``, ``modifiers.py``, ``surfacing.py``, ``exporting.py``, ``raw.py``,
``session.py``): ``conformance_mesh.py``, ``conformance_modifiers.py``,
``conformance_surfacing.py``, ``conformance_exporting.py``, ``conformance_raw.py``,
``conformance_session.py``. This file is the barrel — it re-exports every check plus the two
registries the test files iterate over conceptually (they call checks by name, but the
registries document which set is which).

Most checks are **universal** — they hold for any conforming ``EngineProtocol`` and are
called from both test files. A few are **Blender-only** and are called only from
``blender_test.py``, because ``FakeEngine`` deliberately does not simulate them faithfully:

- ``check_backend_name_identifies_bpy`` — ``FakeEngine.backend_name`` is the literal string
  ``"fake"`` by design (its own docstring says so); only the real backend's name is
  ``"bpy-"``-prefixed.
- ``check_export_gltf_writes_a_nonempty_file`` — ``FakeEngine.export_gltf`` only records the
  call and returns the path; it never touches the filesystem (surfacing is where placement
  and bookkeeping are exercised, not Blender's exporter internals). Only the real exporter's
  file output is testable.

Two checks below deliberately do **not** copy a ``fake_engine_test.py`` assertion verbatim,
because that exact assertion is a ``FakeEngine`` implementation detail rather than part of
``EngineProtocol``'s contract:

- ``check_unwrap_produces_uvs_in_unit_range`` does not assert an exact UV count. Blender
  stores UV coordinates per face-corner (loop), not per vertex; satisfying
  ``MeshSnapshot``'s "one UV per vertex" contract across a seam may require the real
  ``unwrap()`` to split vertices, so vertex count is not guaranteed stable the way
  ``FakeEngine``'s simplified per-vertex UV model keeps it at 8 for a cube.
- ``check_bake_requires_unwrap_first`` asserts an explicit validation *order*: "not
  unwrapped" must be checked, and raised, before any capability-gated bake work is
  attempted. ``FakeEngine`` happens to check its ``bake_supported`` test-knob first (because
  that knob is a fixture convenience, not a real capability probe), but on real ``bpy`` —
  which likely has no windowed context at all (ADR-001) — capability is probably
  *unavailable unconditionally*. Without this ordering requirement, a caller who forgot to
  unwrap would be told "Blender has no window", which has nothing to do with their mistake.
"""

from __future__ import annotations

from .conformance_exporting import check_export_gltf_writes_a_nonempty_file
from .conformance_mesh import (
    check_apply_transform_bakes_scale_into_vertices,
    check_create_mesh_produces_a_closed_manifold,
    check_create_primitive_returns_the_actual_assigned_id,
    check_primitive_has_expected_world_bounds,
    check_unknown_object_error_names_what_exists,
)
from .conformance_modifiers import (
    check_array_along_curve_keeps_instances_plumb_on_a_slope,
    check_array_along_curve_tilts_when_upright_is_disabled,
    check_array_includes_forced_corner_positions,
    check_array_uses_the_caller_supplied_name_template,
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
    check_reset_leaves_zero_objects,
)
from .conformance_surfacing import (
    check_bake_requires_unwrap_first,
    check_bake_succeeds_or_raises_capability_error,
    check_unwrap_produces_uvs_in_unit_range,
)

#: Every check that holds for any conforming ``EngineProtocol``. Both test files call these.
UNIVERSAL_CHECKS = (
    check_primitive_has_expected_world_bounds,
    check_create_mesh_produces_a_closed_manifold,
    check_create_primitive_returns_the_actual_assigned_id,
    check_apply_transform_bakes_scale_into_vertices,
    check_unknown_object_error_names_what_exists,
    check_reset_leaves_zero_objects,
    check_bevel_refuses_unapplied_scale,
    check_bevel_edges_with_explicit_selection_increases_triangle_count,
    check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged,
    check_boolean_union_matches_bounds_and_removes_cutter,
    check_array_along_curve_keeps_instances_plumb_on_a_slope,
    check_array_along_curve_tilts_when_upright_is_disabled,
    check_array_includes_forced_corner_positions,
    check_array_uses_the_caller_supplied_name_template,
    check_merge_by_distance_welds_coincident_vertices,
    check_fill_holes_closes_an_open_box,
    check_fill_holes_reports_what_it_could_not_do,
    check_separate_loose_splits_disconnected_shells,
    check_unwrap_produces_uvs_in_unit_range,
    check_bake_requires_unwrap_first,
    check_bake_succeeds_or_raises_capability_error,
    check_execute_runs_against_live_context,
    check_execute_propagates_a_raising_source,
)

#: Checks that only a real ``bpy`` backend can meaningfully satisfy — see the module
#: docstring for why ``FakeEngine`` is exempt from each. Only ``blender_test.py`` calls these.
BLENDER_ONLY_CHECKS = (
    check_backend_name_identifies_bpy,
    check_export_gltf_writes_a_nonempty_file,
)

__all__ = [
    "UNIVERSAL_CHECKS",
    "BLENDER_ONLY_CHECKS",
    *(fn.__name__ for fn in UNIVERSAL_CHECKS),
    *(fn.__name__ for fn in BLENDER_ONLY_CHECKS),
]
