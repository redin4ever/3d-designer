from __future__ import annotations

from pathlib import Path

import pytest

from contracts import Operation, ToolError, Vec3
from ops.texture_materials import (
    apply_texture_material,
    create_texture_material,
    update_texture_material,
)
from testing import FakeEngine
from textures import TextureLibrary


def _op(kind: str, **params: object) -> Operation:
    return Operation(op_id=f"op-{kind}", kind=kind, params=params)


def _engine() -> FakeEngine:
    engine = FakeEngine()
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.create_primitive("plate", "plane", Vec3(1, 1, 1))
    return engine


def _image(path: Path, payload: bytes = b"texture") -> Path:
    path.write_bytes(payload)
    return path


def test_create_copies_maps_and_registers_engine_material(tmp_path: Path) -> None:
    source = _image(tmp_path / "wood.png")
    root = tmp_path / "managed"
    result = create_texture_material(
        _engine(),
        _op(
            "create_texture_material",
            name="wood_custom",
            managed_root=str(root),
            maps={"albedo": str(source)},
            repeat=[2, 3],
        ),
    )

    assert result.ok
    material = TextureLibrary(root).get("wood_custom")
    assert material.maps[0].path == "wood_custom/albedo.png"
    assert material.transform.repeat == (2.0, 3.0)


def test_update_replaces_managed_maps(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    first = _image(tmp_path / "first.jpg")
    second = _image(tmp_path / "second.webp")
    engine = _engine()
    create_texture_material(
        engine,
        _op("create_texture_material", name="wall", managed_root=str(root), maps={"albedo": str(first)}),
    )

    result = update_texture_material(
        engine,
        _op("update_texture_material", name="wall", managed_root=str(root), maps={"albedo": str(second)}),
    )

    assert result.ok
    assert TextureLibrary(root).get("wall").maps[0].path.endswith("albedo.webp")


def test_apply_validates_every_object_before_mutating(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    source = _image(tmp_path / "stone.png")
    engine = _engine()
    create_texture_material(
        engine,
        _op("create_texture_material", name="stone_custom", managed_root=str(root), maps={"albedo": str(source)}),
    )

    with pytest.raises(ToolError, match="missing"):
        apply_texture_material(
            engine,
            _op(
                "apply_texture_material",
                name="stone_custom",
                managed_root=str(root),
                object_ids=["box", "missing"],
            ),
        )

    assert engine.snapshot("box").material_slots == ()


def test_apply_auto_unwraps_then_assigns_all_objects(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    source = _image(tmp_path / "concrete.png")
    engine = _engine()
    create_texture_material(
        engine,
        _op("create_texture_material", name="concrete_custom", managed_root=str(root), maps={"albedo": str(source)}),
    )

    result = apply_texture_material(
        engine,
        _op(
            "apply_texture_material",
            name="concrete_custom",
            managed_root=str(root),
            object_ids=["box", "plate"],
        ),
    )

    assert result.modified_objects == ("box", "plate")
    assert engine.snapshot("box").uvs is not None
    assert engine.snapshot("box").material_slots == ("concrete_custom",)
    assert engine.snapshot("plate").material_slots == ("concrete_custom",)


def test_builtin_preset_can_be_applied_without_files(tmp_path: Path) -> None:
    engine = _engine()
    result = apply_texture_material(
        engine,
        _op("apply_texture_material", name="brick", managed_root=str(tmp_path / "managed"), object_ids=["box"]),
    )

    assert result.ok
    assert engine.snapshot("box").material_slots == ("brick",)


def test_bad_input_is_tool_error_and_does_not_create_material(tmp_path: Path) -> None:
    engine = _engine()
    with pytest.raises(ToolError):
        create_texture_material(
            engine,
            _op("create_texture_material", name="bad", managed_root=str(tmp_path / "managed"), maps={"albedo": "missing.gif"}),
        )
    assert "bad" not in engine._materials
