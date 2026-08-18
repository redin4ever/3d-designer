"""The blacksmith scene must exercise the reusable silhouette-quality operation."""

from __future__ import annotations

from pathlib import Path


SOURCE = (Path(__file__).parents[2] / "tools" / "create_blacksmith_forge_asset.py").read_text()


def test_forge_uses_profiled_solids_for_hero_silhouettes() -> None:
    assert 'perform("add_profiled_solid"' in SOURCE
    assert 'profiled("anvil_body"' in SOURCE
    assert 'profiled("anvil_face"' in SOURCE
    assert 'profiled("forge_hood"' in SOURCE


def test_crude_primitive_substitutes_do_not_return() -> None:
    for obsolete in (
        'box("anvil_waist"',
        'box("anvil_body"',
        'cone("anvil_horn"',
        'box("hood_back"',
        'box("hood_left"',
        'box("hood_right"',
        'box("hood_top"',
    ):
        assert obsolete not in SOURCE


def test_export_still_preserves_editable_scene_and_portable_model() -> None:
    assert 'blend_path = artifacts / "blacksmith_forge.blend"' in SOURCE
    assert 'glb_path = artifacts / "blacksmith_forge.glb"' in SOURCE
    assert 'engine.export_model(engine.list_objects()' in SOURCE


def test_render_uses_surface_variation_instead_of_flat_debug_colours() -> None:
    assert "def apply_surface_variation" in SOURCE
    assert "ShaderNodeTexNoise" in SOURCE
    assert "ShaderNodeBump" in SOURCE
    for material in ("masonry", "brick", "oak", "iron", "leather"):
        assert f"'{material}'" in SOURCE
