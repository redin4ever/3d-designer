"""End-to-end composition proof for the architectural operations."""

from __future__ import annotations

from contracts import Operation
from app import build_handlers


def test_live_handler_registry_contains_both_architectural_operations() -> None:
    """OPS entries must survive composition into the replay registry used by the live app."""
    handlers = build_handlers(include_raw=False)
    assert "add_gable_roof" in handlers
    assert "add_staircase_to_landing" in handlers


def test_live_handler_coerces_roof_origin_from_json(engine) -> None:
    """The MCP wire sends arrays, so a roof that works only with Python Vec3 values is not
    actually usable by an agent."""
    handler = build_handlers(include_raw=False)["add_gable_roof"]
    result = handler(
        engine,
        Operation(
            op_id="roof-wire",
            kind="add_gable_roof",
            params={
                "object_id":"roof", "origin":[0,0,3], "width":6.0, "depth":8.0,
                "pitch_degrees":30.0, "thickness":0.18, "overhang":0.4,
                "trim_width":0.14, "trim_depth":0.2, "ridge_axis":"y",
            },
        ),
    )
    assert result.ok
    assert engine.exists("roof_ridge_cap")
