"""Real-Blender proof that profiled solids remain closed after engine triangulation/bevel."""

from __future__ import annotations

import pytest

from contracts import Operation, Vec3
from engine import BlenderEngine
from measure import evaluate
from ops import acceptance_for
from ops.profiled_solid import add_profiled_solid

pytestmark = pytest.mark.needs_blender


def test_tapered_profile_is_exact_and_accepted_in_real_blender() -> None:
    engine = BlenderEngine()
    engine.reset()
    try:
        params = {
            "object_id": "hood",
            "origin": Vec3(1.0, -2.0, 3.0),
            "axis": "z",
            "sections": [
                {"offset": 0.0, "profile": [[-1.5, -0.8], [1.5, -0.8], [1.5, 0.8], [-1.5, 0.8]]},
                {"offset": 1.2, "profile": [[-1.5, -0.8], [1.5, -0.8], [1.5, 0.8], [-1.5, 0.8]]},
                {"offset": 2.1, "profile": [[-0.45, -0.35], [0.45, -0.35], [0.45, 0.35], [-0.45, 0.35]]},
            ],
            "bevel_width": 0.02,
        }
        result = add_profiled_solid(
            engine, Operation(op_id="hood-op", kind="add_profiled_solid", params=params)
        )

        assert result.produced_objects == ("hood",)
        bounds = engine.world_bounds("hood")
        assert bounds.minimum.x == pytest.approx(-0.5)
        assert bounds.maximum.x == pytest.approx(2.5)
        assert bounds.minimum.z == pytest.approx(3.0)
        assert bounds.maximum.z == pytest.approx(5.1)
        assert all(
            evaluate(engine, query).passed
            for query in acceptance_for("add_profiled_solid", params, op_id="hood-op")
        )
    finally:
        engine.reset()
