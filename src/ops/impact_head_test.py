"""Contracts for a coherent, fitted dual-strike impact-head assembly."""

from __future__ import annotations

import pytest

from contracts import EPSILON, MetricKind, Operation, ToolError, Vec3
from ops import acceptance_for, joinery_for, runtime_acceptance_for
from ops.impact_head import add_impact_head


def _operation(**overrides) -> Operation:
    params = {
        "object_id": "maul",
        "origin": Vec3(1.5, -0.5, 4.0),
        "width": 3.6,
        "depth": 1.5,
        "height": 1.45,
        "corner_chamfer": 0.22,
        "plate_thickness": 0.12,
        "plate_inset": 0.26,
        "shoulder_depth": 0.38,
        "shoulder_diameter": 0.88,
        "socket_depth": 0.16,
        "collar_depth": 0.20,
        "collar_diameter": 1.24,
        "face_depth": 0.52,
        "face_diameter": 1.62,
        "rim_depth": 0.10,
        "rim_overhang": 0.10,
        "handle_socket_diameter": 0.72,
        "handle_socket_depth": 0.20,
        "handle_collar_depth": 0.18,
        "handle_collar_overhang": 0.10,
        "bevel_width": 0.025,
    }
    params.update(overrides)
    return Operation(op_id="maul-op", kind="add_impact_head", params=params)


def test_add_impact_head_builds_predictable_material_ready_parts(engine) -> None:
    result = add_impact_head(engine, _operation())

    assert result.produced_objects == (
        "maul_body",
        "maul_top_plate",
        "maul_cheek_front",
        "maul_cheek_back",
        "maul_shoulder_left",
        "maul_collar_left",
        "maul_face_left",
        "maul_rim_left",
        "maul_shoulder_right",
        "maul_collar_right",
        "maul_face_right",
        "maul_rim_right",
        "maul_handle_socket",
        "maul_handle_collar",
    )
    assert set(result.produced_objects) == set(engine.list_objects())


def test_armor_plates_are_derived_from_and_touch_the_body(engine) -> None:
    p = _operation().params
    add_impact_head(engine, _operation())

    body = engine.world_bounds("maul_body")
    top = engine.world_bounds("maul_top_plate")
    front = engine.world_bounds("maul_cheek_front")
    back = engine.world_bounds("maul_cheek_back")

    assert top.minimum.z == pytest.approx(body.maximum.z, abs=EPSILON)
    assert top.size.x == pytest.approx(p["width"] - 2 * p["plate_inset"], abs=EPSILON)
    assert top.size.y == pytest.approx(p["depth"] - 2 * p["plate_inset"], abs=EPSILON)
    assert front.maximum.y == pytest.approx(body.minimum.y, abs=EPSILON)
    assert back.minimum.y == pytest.approx(body.maximum.y, abs=EPSILON)
    assert front.size.x == pytest.approx(p["width"] - 2 * p["plate_inset"], abs=EPSILON)
    assert front.size.z == pytest.approx(p["height"] - 2 * p["plate_inset"], abs=EPSILON)


def test_strike_faces_have_socketed_shoulders_and_continuous_transitions(engine) -> None:
    p = _operation().params
    add_impact_head(engine, _operation())

    body = engine.world_bounds("maul_body")
    left_shoulder = engine.world_bounds("maul_shoulder_left")
    left_collar = engine.world_bounds("maul_collar_left")
    left_face = engine.world_bounds("maul_face_left")
    right_shoulder = engine.world_bounds("maul_shoulder_right")
    right_collar = engine.world_bounds("maul_collar_right")
    right_face = engine.world_bounds("maul_face_right")

    assert left_shoulder.maximum.x == pytest.approx(body.minimum.x + p["socket_depth"], abs=EPSILON)
    assert left_collar.maximum.x == pytest.approx(left_shoulder.minimum.x, abs=EPSILON)
    assert left_face.maximum.x == pytest.approx(left_collar.minimum.x, abs=EPSILON)
    assert right_shoulder.minimum.x == pytest.approx(body.maximum.x - p["socket_depth"], abs=EPSILON)
    assert right_collar.minimum.x == pytest.approx(right_shoulder.maximum.x, abs=EPSILON)
    assert right_face.minimum.x == pytest.approx(right_collar.maximum.x, abs=EPSILON)
    assert left_face.size.y == pytest.approx(p["face_diameter"], abs=EPSILON)
    assert right_face.size.z == pytest.approx(p["face_diameter"], abs=EPSILON)


def test_handle_socket_penetrates_body_and_presents_a_fitted_collar(engine) -> None:
    p = _operation().params
    add_impact_head(engine, _operation())

    body = engine.world_bounds("maul_body")
    socket = engine.world_bounds("maul_handle_socket")
    collar = engine.world_bounds("maul_handle_collar")

    assert socket.maximum.z == pytest.approx(body.minimum.z + p["handle_socket_depth"], abs=EPSILON)
    assert socket.minimum.z == pytest.approx(body.minimum.z - p["handle_collar_depth"], abs=EPSILON)
    assert collar.maximum.z == pytest.approx(body.minimum.z, abs=EPSILON)
    assert collar.size.x == pytest.approx(
        p["handle_socket_diameter"] + 2 * p["handle_collar_overhang"], abs=EPSILON,
    )


@pytest.mark.parametrize(
    ("overrides", "rule"),
    (
        ({"plate_inset": 0.10}, "ops.impact_plate_does_not_fit"),
        ({"shoulder_diameter": 1.20}, "ops.impact_shoulder_does_not_fit"),
        ({"collar_diameter": 0.70}, "ops.impact_transition_does_not_fit"),
        ({"handle_socket_diameter": 1.60}, "ops.impact_handle_socket_does_not_fit"),
    ),
)
def test_impossible_proportions_are_rejected_atomically(engine, overrides, rule) -> None:
    with pytest.raises(ToolError) as exc:
        add_impact_head(engine, _operation(**overrides))

    assert exc.value.rule == rule
    assert engine.list_objects() == []


def test_impact_head_acceptance_pins_every_visible_fit_joint() -> None:
    p = _operation().params
    queries = acceptance_for("add_impact_head", p, op_id="maul-op")

    assert len(queries) == 12
    assert all(query.metric is MetricKind.GAP_WIDTH for query in queries)
    subjects = {query.subject for query in queries}
    assert {
        "maul_body|maul_top_plate",
        "maul_body|maul_cheek_front",
        "maul_body|maul_cheek_back",
        "maul_body|maul_shoulder_left",
        "maul_body|maul_shoulder_right",
        "maul_face_left|maul_rim_left",
        "maul_face_right|maul_rim_right",
        "maul_body|maul_handle_socket",
    } <= subjects
    assert runtime_acceptance_for("add_impact_head", p, op_id="maul-op") == queries


def test_impact_head_declares_every_designed_socket_as_joinery() -> None:
    p = _operation().params
    intents = joinery_for("add_impact_head", p)

    assert {(i.object_id, i.into_object_id) for i in intents} == {
        ("maul_shoulder_left", "maul_body"),
        ("maul_shoulder_right", "maul_body"),
        ("maul_rim_left", "maul_face_left"),
        ("maul_rim_right", "maul_face_right"),
        ("maul_handle_socket", "maul_body"),
        ("maul_handle_collar", "maul_handle_socket"),
    }
    by_part = {intent.object_id: intent for intent in intents}
    assert by_part["maul_shoulder_left"].depth == pytest.approx(p["socket_depth"])
    assert by_part["maul_handle_socket"].depth == pytest.approx(p["handle_socket_depth"])
