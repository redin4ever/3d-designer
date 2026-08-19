"""End-to-end reachability for agent-authored profiled solids."""

from __future__ import annotations

from contracts import Operation, ToolRole
from ops import OP_SPECS, OPS
from ops.assumptions_test import _MINIMAL_PARAMS

from app import build_handlers


PARAMS = {
    "object_id": "bracket",
    "origin": [1.0, 2.0, 3.0],
    "axis": "z",
    "sections": [
        {"offset": 0.0, "profile": [[-0.5, -0.3], [0.5, -0.3], [0.5, 0.3], [-0.5, 0.3]]},
        {"offset": 1.2, "profile": [[-0.2, -0.15], [0.2, -0.15], [0.2, 0.15], [-0.2, 0.15]]},
    ],
    "bevel_width": 0.02,
}


def test_profiled_solid_is_replayable_and_publicly_registered() -> None:
    handlers = build_handlers(include_raw=False)

    assert "add_profiled_solid" in OPS
    assert "add_profiled_solid" in handlers


def test_live_handler_accepts_agent_json_and_builds_exact_bounds(engine) -> None:
    handler = build_handlers(include_raw=False)["add_profiled_solid"]
    result = handler(
        engine,
        Operation(op_id="bracket-op", kind="add_profiled_solid", params=PARAMS),
    )

    assert result.ok
    assert result.produced_objects == ("bracket",)
    bounds = engine.world_bounds("bracket")
    assert bounds.minimum.z == 3.0
    assert bounds.maximum.z == 4.2


def test_agent_schema_describes_sections_correspondence_and_units() -> None:
    spec = next(item for item in OP_SPECS if item.name == "add_profiled_solid")

    assert spec.roles == (ToolRole.REFINE,)
    assert spec.input_schema["required"] == [
        "object_id", "origin", "axis", "sections", "bevel_width"
    ]
    sections = spec.input_schema["properties"]["sections"]
    assert sections["minItems"] == 2
    station = sections["items"]
    assert station["required"] == ["offset", "profile"]
    assert "same vertex count" in station["properties"]["profile"]["description"]
    assert "metres" in station["properties"]["offset"]["description"]


def test_profiled_solid_participates_in_no_hidden_assumptions_sweep() -> None:
    assert _MINIMAL_PARAMS["add_profiled_solid"] == PARAMS
