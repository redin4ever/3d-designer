"""The in-memory engine's honest bookkeeping for model-file operations."""

from __future__ import annotations

import pytest

from contracts import EngineError, ModelImportResult
from testing import FakeEngine


def test_fake_import_is_deterministic_and_collision_safe(tmp_path) -> None:
    source = tmp_path / "House.obj"
    source.write_text("o House\n", encoding="utf-8")
    engine = FakeEngine()

    first = engine.import_model(str(source))
    second = engine.import_model(str(source))

    assert isinstance(first, ModelImportResult)
    assert first.object_ids == ("House",)
    assert second.object_ids == ("House.001",)
    assert all(engine.exists(name) for name in (*first.object_ids, *second.object_ids))


def test_fake_import_rejects_bad_inputs_before_touching_the_scene(tmp_path) -> None:
    source = tmp_path / "House.blend"
    source.write_bytes(b"BLENDER")
    engine = FakeEngine()

    with pytest.raises(EngineError, match="supported"):
        engine.import_model(str(source))
    with pytest.raises(EngineError, match="positive"):
        engine.import_model(str(source.with_suffix(".obj")), unit_scale=0)

    assert engine.list_objects() == []


def test_fake_generic_export_records_the_format_and_conversion(tmp_path) -> None:
    source = tmp_path / "House.obj"
    source.write_text("o House\n", encoding="utf-8")
    engine = FakeEngine()
    imported = engine.import_model(str(source))

    result = engine.export_model(
        imported.object_ids,
        str(tmp_path / "house.fbx"),
        y_up=True,
        mirror_x=True,
        negate_rotation=True,
        scale=2.0,
    )

    assert result.endswith("house.fbx")
    assert any(call[0] == "export_model" and call[1][2] == ".fbx" for call in engine.calls)
