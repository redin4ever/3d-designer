"""Universal checks for centered, exportable text geometry."""

from __future__ import annotations

import pytest

from contracts import EngineError, EngineProtocol, Transform, Vec3

__all__ = ["check_create_text_is_centered_mesh", "check_create_text_rejects_empty_text"]


def check_create_text_is_centered_mesh(engine: EngineProtocol) -> None:
    placed = Transform(translation=Vec3(3.0, -2.0, 1.5))
    object_id = engine.create_text("sign", "FORGE WORKS", 0.8, 0.08, placed)

    bounds = engine.world_bounds(object_id)
    snapshot = engine.snapshot(object_id)
    assert bounds.centre.x == pytest.approx(3.0, abs=1e-5)
    assert bounds.centre.y == pytest.approx(-2.0, abs=1e-5)
    assert bounds.centre.z == pytest.approx(1.5, abs=1e-5)
    assert bounds.size.y == pytest.approx(0.8, rel=1e-3)
    assert bounds.size.x > bounds.size.y
    assert bounds.size.z == pytest.approx(0.08, rel=1e-3)
    assert snapshot.triangles, "text must be mesh geometry, not backend-only font data"


def check_create_text_rejects_empty_text(engine: EngineProtocol) -> None:
    with pytest.raises(EngineError) as exc:
        engine.create_text("empty", "   ", 0.8, 0.08)
    assert exc.value.rule == "engine.empty_text"
