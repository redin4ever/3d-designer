"""Public geometry contract for the detailed semantic gable-roof operation."""

from __future__ import annotations

import math

import pytest

from contracts import EPSILON, Operation, Vec3
from measure import find_clipping, gap_width, inspect
from ops import add_gable_roof, joinery_for


def _triangle_shell_count(engine, object_id: str) -> int:
    """Connected triangle components by shared vertex index."""
    triangles = engine.snapshot(object_id).triangles
    remaining = set(range(len(triangles)))
    shells = 0
    while remaining:
        shells += 1
        stack = [remaining.pop()]
        while stack:
            vertices = set(triangles[stack.pop()])
            neighbours = {i for i in remaining if vertices & set(triangles[i])}
            remaining -= neighbours
            stack.extend(neighbours)
    return shells


def _shared_vertex_count(engine, a: str, b: str) -> int:
    """Coincident world vertices prove a full miter face rather than a point contact."""
    def points(object_id: str) -> set[tuple[float, float, float]]:
        return {
            tuple(round(value, 8) for value in vertex.as_tuple())
            for vertex in engine.snapshot(object_id).world_vertices()
        }

    return len(points(a) & points(b))


def _op(*, axis: str = "y") -> Operation:
    return Operation(
        op_id="roof-op",
        kind="add_gable_roof",
        params={
            "object_id": "roof",
            "origin": Vec3(1.0, 2.0, 3.2),
            "width": 10.0,
            "depth": 8.0,
            "pitch_degrees": 30.0,
            "thickness": 0.18,
            "overhang": 0.5,
            "trim_width": 0.16,
            "trim_depth": 0.22,
            "ridge_axis": axis,
        },
    )


def test_gable_roof_builds_panels_ridge_and_all_visible_fascia(engine) -> None:
    """A building roof must arrive as a visibly finished assembly, not two anonymous
    rotated cubes whose ridge and eaves the model has to improvise."""
    result = add_gable_roof(engine, _op())

    assert result.produced_objects == (
        "roof_slope_neg",
        "roof_slope_pos",
        "roof_ridge_cap",
        "roof_gable_neg_trim",
        "roof_gable_pos_trim",
        "roof_eave_neg_fascia",
        "roof_eave_pos_fascia",
    )


def test_gable_panels_meet_at_the_exact_computed_ridge(engine) -> None:
    """The semantic operation owns the pitch arithmetic: both panels must meet at one
    ridge whose height is wall top plus tan(pitch) times half the building span."""
    add_gable_roof(engine, _op())

    expected_ridge = 3.2 + math.tan(math.radians(30.0)) * 5.0
    neg = engine.world_bounds("roof_slope_neg")
    pos = engine.world_bounds("roof_slope_pos")
    assert neg.maximum.z == pytest.approx(expected_ridge + 0.18, abs=EPSILON)
    assert pos.maximum.z == pytest.approx(expected_ridge + 0.18, abs=EPSILON)
    assert gap_width(engine, "roof_slope_neg", "roof_slope_pos").value == pytest.approx(
        0.0, abs=EPSILON
    )


@pytest.mark.parametrize("axis", ["x", "y"])
def test_gable_roof_supports_both_grid_aligned_ridge_axes(engine, axis: str) -> None:
    """A rectangular house rotated ninety degrees must not require quaternion arithmetic
    or a different improvised roof recipe."""
    add_gable_roof(engine, _op(axis=axis))

    ridge = engine.world_bounds("roof_ridge_cap").size
    along = ridge.x if axis == "x" else ridge.y
    across = ridge.y if axis == "x" else ridge.x
    assert along == pytest.approx(9.0, abs=EPSILON)
    assert across == pytest.approx(0.16, abs=EPSILON)


def test_every_roof_part_is_closed_and_individually_valid(engine) -> None:
    """Decorative completeness cannot come at the cost of holes or non-manifold trim that
    later fails export."""
    result = add_gable_roof(engine, _op())

    for object_id in result.produced_objects:
        defects = inspect(engine, object_id)
        assert not defects, (object_id, [d.describe() for d in defects])


def test_white_roof_trim_forms_one_clean_mitered_line_through_the_ridge(engine) -> None:
    """The two rake boards must share a real apex and meet the ridge cap; joining two
    disconnected boxes leaves the visible white outline rough and 86 mm short."""
    add_gable_roof(engine, _op())

    for label in ("neg", "pos"):
        trim = f"roof_gable_{label}_trim"
        assert _triangle_shell_count(engine, trim) == 1
        assert gap_width(engine, "roof_ridge_cap", trim).value == pytest.approx(
            0.0, abs=EPSILON
        )


def test_ridge_cap_finishes_flush_with_the_rake_miter_instead_of_perching_above_it(
    engine,
) -> None:
    """Matching only at one bottom corner still renders as a blunt square block. Their
    visible top planes must finish together so the three white lines read continuously."""
    add_gable_roof(engine, _op())

    ridge_top = engine.world_bounds("roof_ridge_cap").maximum.z
    for label in ("neg", "pos"):
        trim_top = engine.world_bounds(f"roof_gable_{label}_trim").maximum.z
        assert ridge_top == pytest.approx(trim_top, abs=EPSILON)


def test_every_rake_to_eave_corner_is_one_shared_compound_miter_without_cover_blocks(
    engine,
) -> None:
    """A clean roof joins the boards themselves along a full face. Connector blocks hide
    the point contact but remain visibly bulky and are not an acceptable finished edge."""
    result = add_gable_roof(engine, _op())

    assert not any("_cap" in object_id for object_id in result.produced_objects[3:])
    pairs = []
    for gable in ("neg", "pos"):
        for eave in ("neg", "pos"):
            rake = f"roof_gable_{gable}_trim"
            fascia = f"roof_eave_{eave}_fascia"
            pairs.append((rake, fascia))
            assert _shared_vertex_count(engine, rake, fascia) == 4
            assert gap_width(engine, rake, fascia).value == pytest.approx(0.0, abs=EPSILON)
    intents = joinery_for("add_gable_roof", _op().params)
    assert find_clipping(engine, pairs, intents) == ()


def test_compound_corner_miters_remain_full_face_on_a_shallow_small_porch_roof(engine) -> None:
    """The compound miter must remain exact on the shallow 20-degree porch proportions
    that exposed the connector cover's scale-dependent gap."""
    params = {
        **_op().params,
        "object_id": "porch_roof",
        "origin": Vec3(0.0, -5.15, 2.85),
        "width": 3.5,
        "depth": 1.8,
        "pitch_degrees": 20.0,
        "thickness": 0.14,
        "overhang": 0.3,
        "trim_width": 0.13,
        "trim_depth": 0.15,
    }
    add_gable_roof(
        engine, Operation(op_id="porch-roof-op", kind="add_gable_roof", params=params)
    )

    for gable in ("neg", "pos"):
        for eave in ("neg", "pos"):
            rake = f"porch_roof_gable_{gable}_trim"
            fascia = f"porch_roof_eave_{eave}_fascia"
            assert _shared_vertex_count(engine, rake, fascia) == 4
            assert gap_width(engine, rake, fascia).value == pytest.approx(0.0, abs=EPSILON)
