from __future__ import annotations

from pathlib import Path

from app import build_app
from contracts import Operation, Transform, Vec3


def test_live_app_exposes_all_host_aware_surface_operations() -> None:
    app = build_app(prefer_blender=False, include_raw=False, attach_viewer=False)
    assert {"add_roof_window", "add_wall_sign", "add_facade_ribs"} <= set(app.handlers)
    app.engine.create_primitive("wall", "cube", Vec3(5, .2, 3), Transform(translation=Vec3(0, 0, 1.5)))
    result = app.handlers["add_wall_sign"](app.engine, Operation("sign", "add_wall_sign", {
        "object_id": "sign", "wall_id": "wall", "text": "FORGE",
        "toward": [0, -5, 1], "center_height": 2.2,
        "height": 0.3, "depth": 0.03, "edge_margin": 0.1,
    }))
    assert result.ok and result.produced_objects == ("sign",)


def test_factory_generator_uses_semantic_surface_operations_only() -> None:
    source = (Path(__file__).parents[2] / "tools" / "create_factory_asset.py").read_text(encoding="utf-8")
    assert 'perform("add_roof_window"' in source
    assert 'perform("add_wall_sign"' in source
    assert 'perform("add_facade_ribs"' in source
    assert "axis_quat" not in source
    assert "bpy.data.curves.new('ForgeWorksText'" not in source
    assert "front_rib_" not in source
