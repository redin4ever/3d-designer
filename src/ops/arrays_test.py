"""Tests for ``array_along``, ``add_lod_chain``, ``add_modular_kit``.

All three are throwing stubs as of this file (Rule 4 — tests come first); every test below
is expected to fail with ``NotImplementedError`` until the next pass implements them.
"""

from __future__ import annotations

import pytest

from contracts import EPSILON, Operation, Vec3
from ops import add_lod_chain, add_modular_kit, array_along


def test_array_along_places_an_instance_at_every_regular_pitch_point(engine) -> None:
    """An arrayed run that produces the wrong count silently under- or over-fills the
    path it was meant to line — a fence with gaps or a fence with instances stacked on
    top of each other, neither of which a thumbnail render distinguishes from correct."""
    engine.create_primitive("baluster_src", "cube", Vec3(0.05, 0.05, 1.0))
    op = Operation(
        op_id="arr1",
        kind="array_along",
        params={
            "object_id": "baluster_src",
            "path": [Vec3(0, 0, 0), Vec3(4.0, 0, 0)],
            "spacing": 1.0,
        },
    )

    result = array_along(engine, op)

    assert len(result.produced_objects) == 5


def test_lod_chain_each_level_has_strictly_fewer_triangles_than_the_one_before(engine) -> None:
    """A LOD chain that does not strictly shrink defeats the entire point of having one —
    an engine choosing "the simpler version at distance" that turns out no simpler wastes
    a triangle budget for zero benefit, and nobody notices until a performance profile
    does, far downstream of this call."""
    hero_id = engine.create_primitive("hero", "cube", Vec3(1, 1, 1))
    engine.bevel_edges(hero_id, 0.05, segments=3)  # give it geometry worth decimating

    op = Operation(
        op_id="lod1",
        kind="add_lod_chain",
        params={"object_id": hero_id, "ratios": (1.0, 0.5, 0.25, 0.1)},
    )

    result = add_lod_chain(engine, op)

    counts = [engine.snapshot(pid).triangle_count for pid in result.produced_objects]
    for higher, lower in zip(counts, counts[1:]):
        assert lower < higher


def test_lod_chain_level_zero_is_unmodified(engine) -> None:
    """Level 0 exists so the closest camera distance still sees the actual hero mesh — a
    generator that decimates level 0 too (even at "ratio 1.0") silently degrades what was
    supposed to be the one guaranteed-full-detail level."""
    hero_id = engine.create_primitive("hero2", "cube", Vec3(1, 1, 1))
    before = engine.snapshot(hero_id).triangle_count

    op = Operation(
        op_id="lod2",
        kind="add_lod_chain",
        params={"object_id": hero_id, "ratios": (1.0, 0.5)},
    )

    result = add_lod_chain(engine, op)

    level0_id = result.produced_objects[0]
    assert engine.snapshot(level0_id).triangle_count == before


def test_modular_kit_pieces_are_grid_aligned_within_epsilon(engine) -> None:
    """Pieces whose bounds do not snap to the tiling grid leave hairline gaps or overlaps
    at every seam between kit pieces — invisible individually, and the first thing a
    close-up screenshot of a tiled floor shows."""
    grid = 0.5
    op = Operation(
        op_id="kit1",
        kind="add_modular_kit",
        params={
            "object_id": "kit1",
            "grid_size": grid,
            "piece_size": Vec3(0.5, 0.5, 0.1),
            "count_x": 3,
            "count_y": 2,
        },
    )

    result = add_modular_kit(engine, op)

    assert len(result.produced_objects) == 6
    for pid in result.produced_objects:
        bounds = engine.world_bounds(pid)
        for value in (bounds.minimum.x, bounds.minimum.y, bounds.maximum.x, bounds.maximum.y):
            nearest_grid_line = round(value / grid) * grid
            assert value == pytest.approx(nearest_grid_line, abs=EPSILON)
