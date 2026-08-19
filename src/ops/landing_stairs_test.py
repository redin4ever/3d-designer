"""Public geometry contract for landing-connected architectural stairs."""

from __future__ import annotations

import pytest

from contracts import EPSILON, Operation, ToolError, Transform, Vec3
from measure import gap_width, inspect
from ops import add_staircase_to_landing


def _landing(engine, *, center: Vec3 = Vec3(4.0, 1.0, 1.0)) -> None:
    engine.create_primitive(
        "landing", "cube", Vec3(3.0, 3.0, 0.2), Transform(translation=center)
    )


def _op(*, start: Vec3 = Vec3(0.0, 0.0, 0.0), treads: int = 5) -> Operation:
    return Operation(
        op_id="entry-stair-op",
        kind="add_staircase_to_landing",
        params={
            "object_id": "entry_stair",
            "landing_id": "landing",
            "start": start,
            "treads": treads,
            "width": 1.2,
            "tread_thickness": 0.06,
            "stringer_width": 0.12,
            "stringer_depth": 0.22,
        },
    )


def test_landing_stair_builds_requested_treads_and_two_stringers(engine) -> None:
    """A house stair is a supported assembly, not a loose row of blocks suspended in front
    of a porch."""
    _landing(engine)
    result = add_staircase_to_landing(engine, _op())

    assert result.produced_objects == (
        "entry_stair_tread_000",
        "entry_stair_tread_001",
        "entry_stair_tread_002",
        "entry_stair_tread_003",
        "entry_stair_tread_004",
        "entry_stair_stringer_left",
        "entry_stair_stringer_right",
    )


def test_highest_tread_meets_the_live_landing_top_and_edge(engine) -> None:
    """The tool—not the model—owns the spatial arithmetic that makes the final tread meet
    both the landing elevation and its nearest boundary."""
    _landing(engine)
    add_staircase_to_landing(engine, _op())

    landing = engine.world_bounds("landing")
    top = engine.world_bounds("entry_stair_tread_004")
    assert top.maximum.z == pytest.approx(landing.maximum.z, abs=EPSILON)
    assert gap_width(engine, "entry_stair_tread_004", "landing").value == pytest.approx(
        0.0, abs=EPSILON
    )


def test_stair_direction_is_derived_from_start_to_landing_not_fixed_world_x(engine) -> None:
    """A landing offset in Y must produce a diagonal run toward it; the legacy fixed +X
    assumption is the root of stairs appearing beside rather than against a porch."""
    _landing(engine, center=Vec3(4.0, 4.0, 1.0))
    add_staircase_to_landing(engine, _op())

    first = engine.world_bounds("entry_stair_tread_000")
    last = engine.world_bounds("entry_stair_tread_004")
    first_center = (first.minimum + first.maximum) * 0.5
    last_center = (last.minimum + last.maximum) * 0.5
    assert last_center.x > first_center.x
    assert last_center.y > first_center.y


def test_every_stair_part_is_closed_and_individually_valid(engine) -> None:
    """Adding visual support must not introduce self-intersections or open stringers."""
    _landing(engine)
    result = add_staircase_to_landing(engine, _op())

    for object_id in result.produced_objects:
        assert not inspect(engine, object_id), object_id


@pytest.mark.parametrize(
    "center,start,rule",
    [
        (Vec3(4.0, 0.0, -0.2), Vec3(), "landing_not_above_start"),
        (Vec3(0.0, 0.0, 1.0), Vec3(), "start_inside_landing"),
    ],
)
def test_unreachable_or_degenerate_landing_refuses_without_orphans(
    engine, center: Vec3, start: Vec3, rule: str
) -> None:
    """A bad relationship is rejected before one tread appears, so retries cannot leave a
    trail of malformed stair fragments in the scene."""
    _landing(engine, center=center)

    with pytest.raises(ToolError) as exc:
        add_staircase_to_landing(engine, _op(start=start))

    assert exc.value.rule == f"ops.{rule}"
    assert engine.list_objects() == ["landing"]
