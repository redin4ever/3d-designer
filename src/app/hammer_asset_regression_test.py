"""The reported hammer must exercise the semantic head operation in a real artifact."""

from __future__ import annotations

from pathlib import Path


SOURCE = (Path(__file__).parents[2] / "tools" / "create_hammer_asset.py").read_text(
    encoding="utf-8"
)


def test_hammer_generator_uses_the_fitted_impact_head_operation() -> None:
    assert 'perform("add_impact_head"' in SOURCE
    assert 'box("head_top_rail"' not in SOURCE
    assert 'box("head_bottom_rail"' not in SOURCE
    assert 'primitive(f"strike_face_' not in SOURCE
    assert 'primitive(f"claw_' not in SOURCE
    assert 'box(f"status_fin_' not in SOURCE


def test_hammer_generator_assigns_materials_to_semantic_part_families() -> None:
    for family in (
        "hero_head_body", "hero_head_top_plate", "hero_head_cheek_",
        "hero_head_shoulder_", "hero_head_collar_", "hero_head_face_",
        "hero_head_striker_", "hero_head_rim_", "hero_head_handle_socket",
        "hero_head_handle_collar",
    ):
        assert family in SOURCE
