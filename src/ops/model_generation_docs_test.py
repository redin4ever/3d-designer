"""The semantic mechanical workflow must be discoverable without reading implementation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]
FEATURE = (ROOT / "docs/features/model-generation-quality/FEATURE.md").read_text(encoding="utf-8")
OPS_README = (ROOT / "src/ops/README.md").read_text(encoding="utf-8")


def test_feature_record_explains_the_impact_head_workflow_and_fit_contract() -> None:
    assert "add_impact_head" in FEATURE
    assert "hero_head_top_plate" in FEATURE
    assert "hero_head_striker_left" in FEATURE
    assert "14 zero-gap" in FEATURE
    assert "futuristic_hammer.png" in FEATURE


def test_construction_library_lists_the_semantic_mechanical_operation() -> None:
    assert "add_impact_head" in OPS_README
    assert "socketed" in OPS_README
