"""Executable acceptance and explicit joinery for semantic architecture."""

from __future__ import annotations

from contracts import Operation, Vec3
from measure import evaluate
from ops import acceptance_for, add_floor, add_gable_roof, add_staircase_to_landing, joinery_for


def _roof_params() -> dict:
    return {
        "object_id": "roof", "origin": Vec3(0, 0, 2.8), "width": 6.0,
        "depth": 8.0, "pitch_degrees": 32.0, "thickness": 0.18,
        "overhang": 0.4, "trim_width": 0.14, "trim_depth": 0.18,
        "ridge_axis": "y",
    }


def _stair_params() -> dict:
    return {
        "object_id": "entry", "landing_id": "porch", "start": Vec3(0, -3, 0),
        "treads": 6, "width": 1.4, "tread_thickness": 0.05,
        "stringer_width": 0.12, "stringer_depth": 0.2,
    }


def test_gable_roof_acceptance_remeasures_every_critical_roof_joint(engine) -> None:
    params = _roof_params()
    add_gable_roof(engine, Operation(op_id="roof-op", kind="add_gable_roof", params=params))

    queries = acceptance_for("add_gable_roof", params, op_id="roof-op")

    assert {q.subject for q in queries} == {
        "roof_slope_neg|roof_slope_pos",
        "roof_ridge_cap|roof_slope_neg",
        "roof_ridge_cap|roof_slope_pos",
        "roof_ridge_cap|roof_gable_neg_trim",
        "roof_ridge_cap|roof_gable_pos_trim",
        "roof_gable_neg_trim|roof_eave_neg_fascia",
        "roof_gable_neg_trim|roof_eave_pos_fascia",
        "roof_gable_pos_trim|roof_eave_neg_fascia",
        "roof_gable_pos_trim|roof_eave_pos_fascia",
    }
    assert all(evaluate(engine, query).passed for query in queries)


def test_landing_stair_acceptance_remeasures_the_top_tread_to_landing_joint(engine) -> None:
    add_floor(
        engine,
        Operation(
            op_id="porch-op", kind="add_floor",
            params={
                "object_id": "porch", "width": 3.0, "depth": 2.0,
                "thickness": 0.2, "origin": Vec3(0, 0, 1.1),
            },
        ),
    )
    params = _stair_params()
    add_staircase_to_landing(
        engine, Operation(op_id="entry-op", kind="add_staircase_to_landing", params=params)
    )

    queries = acceptance_for("add_staircase_to_landing", params, op_id="entry-op")

    assert len(queries) == 1
    assert queries[0].subject == "entry_tread_005|porch"
    assert evaluate(engine, queries[0]).passed


def test_landing_stair_joinery_explicitly_declares_each_supported_tread_contact() -> None:
    intents = joinery_for("add_staircase_to_landing", _stair_params())

    assert len(intents) == 12
    assert {intent.object_id for intent in intents} == {
        "entry_stringer_left", "entry_stringer_right",
    }
    assert {intent.into_object_id for intent in intents} == {
        f"entry_tread_{i:03d}" for i in range(6)
    }
    assert all(intent.axis == "z" and intent.reason for intent in intents)


def test_roof_joinery_declares_the_ridge_cap_overlap_that_blends_the_white_trim() -> None:
    intents = joinery_for("add_gable_roof", _roof_params())

    assert len(intents) == 6
    assert {intent.object_id for intent in intents} == {
        "roof_ridge_cap", "roof_gable_neg_trim", "roof_gable_pos_trim",
    }
    assert {intent.into_object_id for intent in intents} == {
        "roof_slope_neg", "roof_slope_pos",
        "roof_eave_neg_fascia", "roof_eave_pos_fascia",
    }
    assert all(intent.axis == "z" and intent.depth > 0 and intent.reason for intent in intents)
