"""Discoverability contract for section-based solid modelling."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]
FEATURE = (ROOT / "docs/features/profiled-shape-design-accuracy/FEATURE.md").read_text()
OPS_README = (ROOT / "src/ops/README.md").read_text()


def test_feature_record_explains_geometry_and_failure_contracts() -> None:
    for phrase in (
        "add_profiled_solid",
        "counter-clockwise",
        "same vertex count",
        "strictly increasing",
        "atomically",
        "positive volume",
        "self-intersection",
    ):
        assert phrase in FEATURE


def test_feature_record_shows_general_uses_not_only_the_forge() -> None:
    for example in ("anvil", "extraction hood", "architecture", "furniture"):
        assert example in FEATURE


def test_ops_readme_exposes_profiled_solids_beside_other_construction_tools() -> None:
    assert "add_profiled_solid(engine, op)" in OPS_README
    assert "profiled_solid.py" in OPS_README
