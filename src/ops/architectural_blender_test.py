"""Real-Blender proof for the semantic architectural operations."""

from __future__ import annotations

import pytest

from contracts import Operation, Vec3
from engine import BlenderEngine
from measure import evaluate, find_clipping, gap_width
from ops import (
    acceptance_for,
    add_floor,
    add_gable_roof,
    add_staircase_to_landing,
    joinery_for,
)

pytestmark = pytest.mark.needs_blender


def test_roof_and_supported_entry_stairs_hold_their_contract_in_real_blender() -> None:
    engine = BlenderEngine()
    engine.reset()
    try:
        roof_params = {
            "object_id": "roof", "origin": Vec3(0, 0, 2.8), "width": 6.0,
            "depth": 8.0, "pitch_degrees": 32.0, "thickness": 0.18,
            "overhang": 0.4, "trim_width": 0.14, "trim_depth": 0.18,
            "ridge_axis": "y",
        }
        roof = add_gable_roof(
            engine, Operation(op_id="roof-op", kind="add_gable_roof", params=roof_params)
        )

        add_floor(
            engine,
            Operation(
                op_id="porch-op", kind="add_floor",
                params={
                    "object_id": "porch", "width": 3.0, "depth": 2.0,
                    "thickness": 0.2, "origin": Vec3(0, -5, 1.1),
                },
            ),
        )
        stair_params = {
            "object_id": "entry", "landing_id": "porch", "start": Vec3(0, -7, 0),
            "treads": 6, "width": 1.4, "tread_thickness": 0.05,
            "stringer_width": 0.12, "stringer_depth": 0.2,
        }
        stairs = add_staircase_to_landing(
            engine,
            Operation(op_id="entry-op", kind="add_staircase_to_landing", params=stair_params),
        )

        assert len(roof.produced_objects) == 7
        assert len(stairs.produced_objects) == 8
        queries = (
            *acceptance_for("add_gable_roof", roof_params, op_id="roof-op"),
            *acceptance_for("add_staircase_to_landing", stair_params, op_id="entry-op"),
        )
        assert all(evaluate(engine, query).passed for query in queries)

        roof_intents = joinery_for("add_gable_roof", roof_params)
        roof_pairs = tuple(
            (intent.object_id, intent.into_object_id) for intent in roof_intents
        )
        assert find_clipping(engine, roof_pairs, roof_intents) == ()

        intents = joinery_for("add_staircase_to_landing", stair_params)
        pairs = tuple((intent.object_id, intent.into_object_id) for intent in intents)
        assert all(gap_width(engine, a, b).value <= 1e-4 for a, b in pairs)
        assert find_clipping(engine, pairs, intents) == ()
    finally:
        engine.reset()
