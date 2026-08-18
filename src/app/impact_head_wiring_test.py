"""End-to-end reachability proof for semantic impact-head construction."""

from __future__ import annotations

from app import build_handlers
from contracts import Operation, ToolRole
from ops import OP_SPECS
from ops.assumptions_test import _MINIMAL_PARAMS


def _params() -> dict:
    return {
        "object_id": "maul", "origin": [0, 0, 4], "width": 3.6, "depth": 1.5,
        "height": 1.45, "corner_chamfer": 0.22, "plate_thickness": 0.12,
        "plate_inset": 0.26, "shoulder_depth": 0.38, "shoulder_diameter": 0.88,
        "socket_depth": 0.16, "collar_depth": 0.20, "collar_diameter": 1.24,
        "face_depth": 0.52, "face_diameter": 1.62, "striker_depth": 0.12,
        "striker_socket_depth": 0.05, "striker_diameter": 0.82, "rim_depth": 0.10,
        "rim_overhang": 0.10, "handle_socket_diameter": 0.72,
        "handle_socket_depth": 0.20, "handle_collar_depth": 0.18,
        "handle_collar_overhang": 0.10, "bevel_width": 0.025,
    }


def test_live_handler_builds_impact_head_from_agent_json(engine) -> None:
    handler = build_handlers(include_raw=False)["add_impact_head"]
    result = handler(
        engine,
        Operation(op_id="maul-wire", kind="add_impact_head", params=_params()),
    )

    assert result.ok
    assert engine.exists("maul_body")
    assert engine.exists("maul_face_left")
    assert engine.exists("maul_face_right")


def test_impact_head_is_a_refine_tool_with_a_complete_schema() -> None:
    spec = next(item for item in OP_SPECS if item.name == "add_impact_head")
    assert spec.roles == (ToolRole.REFINE,)
    assert set(spec.input_schema["required"]) == set(_params())


def test_impact_head_participates_in_the_no_hidden_assumptions_sweep() -> None:
    assert _MINIMAL_PARAMS["add_impact_head"] == _params()
