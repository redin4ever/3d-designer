"""Contract tests for reusable extrusion and variable-section loft construction."""

from __future__ import annotations

import pytest

from contracts import DefectClass, MetricKind, Operation, ToolError, Vec3
from measure import (
    find_boundary_holes,
    find_flipped_normals,
    find_loose_or_duplicate,
    find_non_manifold_edges,
    find_non_manifold_vertices,
)
from ops import acceptance_for, runtime_acceptance_for
from ops.profiled_solid import add_profiled_solid


RECTANGLE = [[-0.5, -0.25], [0.5, -0.25], [0.5, 0.25], [-0.5, 0.25]]


def _operation(**overrides) -> Operation:
    params = {
        "object_id": "formed",
        "origin": Vec3(2.0, 3.0, 4.0),
        "axis": "x",
        "sections": [
            {"offset": -1.0, "profile": RECTANGLE},
            {"offset": 1.0, "profile": RECTANGLE},
        ],
        "bevel_width": 0.0,
    }
    params.update(overrides)
    return Operation(op_id="formed-op", kind="add_profiled_solid", params=params)


def test_identical_sections_make_one_exact_closed_extrusion(engine) -> None:
    result = add_profiled_solid(engine, _operation())

    assert result.produced_objects == ("formed",)
    bounds = engine.world_bounds("formed")
    assert bounds.minimum == Vec3(1.0, 2.5, 3.75)
    assert bounds.maximum == Vec3(3.0, 3.5, 4.25)
    assert find_boundary_holes(engine, "formed") == ()
    assert find_non_manifold_edges(engine, "formed") == ()
    assert find_non_manifold_vertices(engine, "formed") == ()
    assert find_loose_or_duplicate(engine, "formed") == ()
    assert find_flipped_normals(engine, "formed") == ()


@pytest.mark.parametrize(
    ("axis", "expected_minimum", "expected_maximum"),
    (
        ("x", Vec3(1.0, 2.5, 3.75), Vec3(3.0, 3.5, 4.25)),
        ("y", Vec3(1.5, 2.0, 3.75), Vec3(2.5, 4.0, 4.25)),
        ("z", Vec3(1.5, 2.75, 3.0), Vec3(2.5, 3.25, 5.0)),
    ),
)
def test_all_world_axes_preserve_declared_station_and_profile_bounds(
    engine, axis, expected_minimum, expected_maximum
) -> None:
    add_profiled_solid(engine, _operation(axis=axis))

    bounds = engine.world_bounds("formed")
    assert bounds.minimum == expected_minimum
    assert bounds.maximum == expected_maximum


def test_variable_sections_form_a_continuous_taper_without_extra_parts(engine) -> None:
    small = [[-0.2, -0.1], [0.2, -0.1], [0.2, 0.1], [-0.2, 0.1]]
    result = add_profiled_solid(
        engine,
        _operation(sections=[
            {"offset": -1.0, "profile": RECTANGLE},
            {"offset": 0.2, "profile": RECTANGLE},
            {"offset": 1.4, "profile": small},
        ]),
    )

    assert result.produced_objects == ("formed",)
    assert engine.world_bounds("formed").maximum.x == pytest.approx(3.4)
    assert len(engine.snapshot("formed").triangles) == 20
    assert find_boundary_holes(engine, "formed") == ()


@pytest.mark.parametrize(
    ("overrides", "rule"),
    (
        ({"axis": "diagonal"}, "ops.profiled_bad_axis"),
        ({"sections": [{"offset": 0.0, "profile": RECTANGLE}]}, "ops.profiled_station_count"),
        ({"sections": [
            {"offset": 0.0, "profile": RECTANGLE},
            {"offset": 0.0, "profile": RECTANGLE},
        ]}, "ops.profiled_station_order"),
        ({"sections": [
            {"offset": 0.0, "profile": RECTANGLE},
            {"offset": 1.0, "profile": RECTANGLE[:3]},
        ]}, "ops.profiled_correspondence"),
        ({"sections": [
            {"offset": 0.0, "profile": RECTANGLE},
            {"offset": 1.0, "profile": list(reversed(RECTANGLE))},
        ]}, "ops.profiled_winding"),
        ({"sections": [
            {"offset": 0.0, "profile": [[0, 0], [1, 0], [0.4, 0.3], [1, 1], [0, 1]]},
            {"offset": 1.0, "profile": [[0, 0], [1, 0], [0.4, 0.3], [1, 1], [0, 1]]},
        ]}, "ops.profiled_non_convex"),
        ({"bevel_width": 0.30}, "ops.profiled_bevel_does_not_fit"),
    ),
)
def test_invalid_shape_contracts_reject_atomically(engine, overrides, rule) -> None:
    with pytest.raises(ToolError) as exc:
        add_profiled_solid(engine, _operation(**overrides))

    assert exc.value.rule == rule
    assert engine.list_objects() == []


def test_malformed_json_profile_names_the_station_and_point(engine) -> None:
    sections = [
        {"offset": 0.0, "profile": RECTANGLE},
        {"offset": 1.0, "profile": [[-0.5, -0.25], ["wide", -0.25], [0.5, 0.25], [-0.5, 0.25]]},
    ]

    with pytest.raises(ToolError) as exc:
        add_profiled_solid(engine, _operation(sections=sections))

    assert exc.value.rule == "ops.profiled_bad_point"
    assert "section 1 point 1" in exc.value.detail


def test_positive_bevel_is_applied_only_after_the_mesh_exists(engine) -> None:
    add_profiled_solid(engine, _operation(bevel_width=0.02))

    names = [name for name, _args in engine.calls]
    assert names.index("create_mesh") < names.index("bevel_edges")


def test_acceptance_gates_volume_and_every_structural_topology_class() -> None:
    params = _operation().params
    queries = acceptance_for("add_profiled_solid", params, op_id="formed-op")

    assert len(queries) == 2
    assert queries[0].metric is MetricKind.VOLUME
    assert queries[1].forbidden_defects == (
        DefectClass.BOUNDARY_HOLE,
        DefectClass.NON_MANIFOLD_EDGE,
        DefectClass.NON_MANIFOLD_VERTEX,
        DefectClass.LOOSE_OR_DUPLICATE,
        DefectClass.FLIPPED_NORMAL,
        DefectClass.SELF_INTERSECTION,
    )
    assert runtime_acceptance_for("add_profiled_solid", params, op_id="formed-op") == queries
