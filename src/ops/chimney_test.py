"""Contracts for a complete architectural chimney assembly."""

from __future__ import annotations

import pytest

from contracts import EPSILON, Operation, ToolError, Vec3
from ops import add_chimney
from testing import connected_components


def _operation(**overrides) -> Operation:
    params = {
        "object_id": "chimney",
        "origin": Vec3(2.65, 0.55, 3.65),
        "width": 0.9,
        "depth": 1.1,
        "shaft_height": 1.5,
        "flashing_overhang": 0.2,
        "flashing_height": 0.18,
        "crown_overhang": 0.1,
        "crown_height": 0.14,
        "flue_count": 2,
        "flue_radius": 0.12,
        "flue_height": 0.56,
        "rim_overhang": 0.035,
        "rim_height": 0.12,
    }
    params.update(overrides)
    return Operation(op_id="chimney-op", kind="add_chimney", params=params)


def test_add_chimney_builds_shaft_flashing_crown_and_finished_flues(engine) -> None:
    """A chimney is not one tall cube: its roof junction, weathering crown, and flue
    terminations are the details that make the mass read as an intentional assembly."""
    result = add_chimney(engine, _operation())

    assert result.produced_objects == (
        "chimney_shaft",
        "chimney_flashing",
        "chimney_crown",
        "chimney_flue_000",
        "chimney_flue_000_rim",
        "chimney_flue_001",
        "chimney_flue_001_rim",
    )
    flashing = engine.snapshot("chimney_flashing")
    assert len(flashing.triangles) > 12, "flashing must be a shaped collar, not another cube"
    assert len(connected_components(len(flashing.vertices), flashing.triangles)) == 1


def test_add_chimney_respects_crown_overhang_and_vertical_stack(engine) -> None:
    add_chimney(engine, _operation())

    shaft = engine.world_bounds("chimney_shaft")
    crown = engine.world_bounds("chimney_crown")
    flue = engine.world_bounds("chimney_flue_000")
    rim = engine.world_bounds("chimney_flue_000_rim")

    assert crown.size.x == pytest.approx(shaft.size.x + 0.2, abs=EPSILON)
    assert crown.size.y == pytest.approx(shaft.size.y + 0.2, abs=EPSILON)
    assert crown.minimum.z == pytest.approx(shaft.maximum.z, abs=EPSILON)
    assert flue.minimum.z == pytest.approx(crown.maximum.z, abs=EPSILON)
    assert rim.minimum.z == pytest.approx(flue.maximum.z, abs=EPSILON)


def test_add_chimney_refuses_flues_that_do_not_fit_before_creating_geometry(engine) -> None:
    with pytest.raises(ToolError) as exc:
        add_chimney(engine, _operation(flue_count=4, flue_radius=0.24, rim_overhang=0.08))

    assert exc.value.rule == "ops.chimney_flues_do_not_fit"
    assert "flue" in exc.value.detail
    assert engine.list_objects() == []
