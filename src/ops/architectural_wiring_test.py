"""Registry, schema and validation contract for semantic architectural operations."""

from __future__ import annotations

import pytest

from contracts import ToolError, ToolRole, Vec3
from ops import OP_SPECS, OPS, validate_params


def _spec(name: str):
    return next(spec for spec in OP_SPECS if spec.name == name)


def test_architectural_operations_are_registered_with_their_correct_phases() -> None:
    """Correct geometry that is absent from OPS or exposed in the wrong phase remains
    unavailable to the model, which then falls back to raw primitives again."""
    assert "add_gable_roof" in OPS
    assert "add_staircase_to_landing" in OPS
    assert _spec("add_gable_roof").roles == (ToolRole.BLOCKOUT,)
    assert _spec("add_staircase_to_landing").roles == (ToolRole.REFINE,)


def test_gable_roof_schema_exposes_every_visual_design_dimension() -> None:
    """Pitch, overhang and trim cannot be hidden defaults if the agent is responsible for
    the design's appearance."""
    spec = _spec("add_gable_roof")
    required = set(spec.input_schema["required"])
    assert required == {
        "object_id", "origin", "width", "depth", "pitch_degrees", "thickness",
        "overhang", "trim_width", "trim_depth", "ridge_axis",
    }
    assert spec.input_schema["properties"]["ridge_axis"]["enum"] == ["x", "y"]
    assert "rotated cube" in spec.description.lower()


def test_landing_stair_schema_names_the_relationship_instead_of_raw_run_math() -> None:
    """The model should name the landing and bottom start; rise, run and direction are
    deliberately absent because the tool derives them from live geometry."""
    required = set(_spec("add_staircase_to_landing").input_schema["required"])
    assert required == {
        "object_id", "landing_id", "start", "treads", "width", "tread_thickness",
        "stringer_width", "stringer_depth",
    }
    assert not ({"rise", "run", "direction"} & required)


@pytest.mark.parametrize(
    "kind,params,rule",
    [
        ("add_gable_roof", {"object_id":"r","origin":Vec3(),"width":4.0,"depth":5.0,
         "pitch_degrees":90.0,"thickness":0.2,"overhang":0.3,"trim_width":0.1,
         "trim_depth":0.1,"ridge_axis":"y"}, "ops.bad_pitch"),
        ("add_staircase_to_landing", {"object_id":"s","landing_id":"deck","start":Vec3(),
         "treads":0,"width":1.0,"tread_thickness":0.05,"stringer_width":0.1,
         "stringer_depth":0.2}, "ops.non_positive_count"),
    ],
)
def test_architectural_validation_refuses_impossible_calls_by_named_rule(
    kind: str, params: dict, rule: str
) -> None:
    """Malformed architecture must fail at the boundary with a fixable rule, not inside
    mesh construction after partial objects exist."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)
    assert exc.value.rule == rule
