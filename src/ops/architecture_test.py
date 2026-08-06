"""Tests for ``add_wall``, ``add_floor``, ``add_opening`` — the architectural shell
operations blockout starts from.

All three are throwing stubs as of this file (Rule 4 — tests come first); every test below
is expected to fail with ``NotImplementedError`` until the next pass implements them.
"""

from __future__ import annotations

import pytest

from contracts import EPSILON, Operation, ToolError, Vec3
from ops import add_floor, add_opening, add_wall


def test_add_wall_produces_the_requested_height_and_thickness(engine) -> None:
    """A wall built at the wrong height silently under- or over-shoots the ceiling it is
    meant to meet — invisible from the default camera angle used in every screenshot, and
    exactly the kind of defect only a world-bounds measurement catches."""
    op = Operation(
        op_id="wall1",
        kind="add_wall",
        params={
            "object_id": "wall1",
            "start": Vec3(0, 0, 0),
            "end": Vec3(4.0, 0, 0),
            "height": 2.4,
            "thickness": 0.2,
        },
    )

    result = add_wall(engine, op)

    wall_id = result.produced_objects[0]
    size = engine.world_bounds(wall_id).size
    assert size.z == pytest.approx(2.4, abs=EPSILON)
    assert min(size.x, size.y) == pytest.approx(0.2, abs=EPSILON)


def test_add_wall_length_matches_the_distance_from_start_to_end(engine) -> None:
    """A wall whose built length does not match ``start``/``end`` leaves a gap or overlap
    at the next wall it is meant to meet corner-to-corner — a defect a floor-plan
    dimension check would catch immediately and a thumbnail render would not."""
    op = Operation(
        op_id="wall2",
        kind="add_wall",
        params={
            "object_id": "wall2",
            "start": Vec3(0, 0, 0),
            "end": Vec3(5.0, 0, 0),
            "height": 2.4,
            "thickness": 0.2,
        },
    )

    result = add_wall(engine, op)

    wall_id = result.produced_objects[0]
    size = engine.world_bounds(wall_id).size
    assert max(size.x, size.y) == pytest.approx(5.0, abs=EPSILON)


def test_add_floor_produces_the_requested_footprint_and_thickness(engine) -> None:
    """A floor slab thinner or shallower than requested either clips through whatever is
    meant to rest on it or leaves a visible gap at its own edge — both invisible from
    above, both caught only by measuring the built slab's own world bounds."""
    op = Operation(
        op_id="floor1",
        kind="add_floor",
        params={"object_id": "floor1", "width": 5.0, "depth": 3.0, "thickness": 0.15},
    )

    result = add_floor(engine, op)

    floor_id = result.produced_objects[0]
    size = engine.world_bounds(floor_id).size
    assert size.x == pytest.approx(5.0, abs=EPSILON)
    assert size.y == pytest.approx(3.0, abs=EPSILON)
    assert size.z == pytest.approx(0.15, abs=EPSILON)


def test_opening_removes_volume_from_the_wall(engine) -> None:
    """An opening that does not actually change the wall's own geometry is a door an
    agent believes it cut and a person in-engine will walk into — it passes every manifold
    check because the wall is still a perfectly valid, perfectly solid mesh."""
    wall_id = engine.create_primitive("wall_src", "cube", Vec3(0.2, 4.0, 2.5))
    before_tris = engine.snapshot(wall_id).triangle_count

    op = Operation(
        op_id="open1",
        kind="add_opening",
        params={
            "object_id": "open1",
            "wall_id": wall_id,
            "position": 2.0,
            "width": 0.9,
            "height": 2.0,
        },
    )

    result = add_opening(engine, op)

    after_tris = engine.snapshot(wall_id).triangle_count
    assert after_tris != before_tris, "a boolean cut must change the wall's own triangle count"
    assert wall_id in result.modified_objects


def test_opening_entirely_outside_the_wall_raises_tool_error(engine) -> None:
    """A cut position past the wall's own extent must never silently do nothing — an
    agent that gets ``ok=True`` back for a call that changed nothing will report the door
    as built when the wall is still solid, and nobody re-checks a call that claimed
    success."""
    wall_id = engine.create_primitive("wall_src2", "cube", Vec3(0.2, 4.0, 2.5))

    op = Operation(
        op_id="open2",
        kind="add_opening",
        params={
            "object_id": "open2",
            "wall_id": wall_id,
            "position": 50.0,
            "width": 0.9,
            "height": 2.0,
        },
    )

    with pytest.raises(ToolError):
        add_opening(engine, op)
