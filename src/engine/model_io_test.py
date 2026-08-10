from __future__ import annotations

from pathlib import Path

import pytest

from contracts import EngineError, SUPPORTED_MODEL_EXTENSIONS
from engine.model_io import ModelIOMixin, export_operator_for_suffix, import_operator_for_suffix


def test_dispatch_covers_every_frozen_model_extension() -> None:
    assert set(SUPPORTED_MODEL_EXTENSIONS) == {
        ".glb", ".gltf", ".fbx", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc",
    }
    for suffix in SUPPORTED_MODEL_EXTENSIONS:
        assert import_operator_for_suffix(suffix)
        assert export_operator_for_suffix(suffix)


@pytest.mark.parametrize("path", ["missing.obj", "mesh.blend", "mesh.txt"])
def test_import_validates_existing_supported_local_files(tmp_path: Path, path: str) -> None:
    target = tmp_path / path
    if target.name != "missing.obj":
        target.write_text("not a supported model", encoding="utf-8")

    with pytest.raises(EngineError):
        ModelIOMixin().import_model(str(target))


@pytest.mark.parametrize("source_up", ["BAD", "W"])
def test_import_rejects_invalid_axis_override(tmp_path: Path, source_up: str) -> None:
    target = tmp_path / "mesh.obj"
    target.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")

    with pytest.raises(EngineError, match="engine.invalid_source_up"):
        ModelIOMixin().import_model(str(target), source_up=source_up)


def test_import_rejects_non_positive_unit_scale(tmp_path: Path) -> None:
    target = tmp_path / "mesh.obj"
    target.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")

    with pytest.raises(EngineError, match="engine.bad_import_scale"):
        ModelIOMixin().import_model(str(target), unit_scale=0.0)


@pytest.mark.needs_blender
def test_import_is_atomic_and_keeps_collision_renamed_mesh(tmp_path: Path) -> None:
    bpy = pytest.importorskip("bpy")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    existing = bpy.data.meshes.new("existing_mesh")
    existing.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    existing_obj = bpy.data.objects.new("mesh", existing)
    bpy.context.scene.collection.objects.link(existing_obj)

    target = tmp_path / "mesh.obj"
    target.write_text("o mesh\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    result = ModelIOMixin().import_model(str(target), flatten=True)

    assert result.object_ids
    assert result.object_ids[0] != "mesh"
    assert result.object_ids[0].startswith("mesh.")
    assert all(bpy.data.objects[name].type == "MESH" for name in result.object_ids)


@pytest.mark.needs_blender
def test_import_with_no_meshes_rolls_back_created_objects(tmp_path: Path) -> None:
    bpy = pytest.importorskip("bpy")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    target = tmp_path / "empty.obj"
    target.write_text("o empty\n", encoding="utf-8")

    with pytest.raises(EngineError, match="engine.model_import_no_meshes"):
        ModelIOMixin().import_model(str(target))
    assert list(bpy.data.objects) == []


@pytest.mark.needs_blender
def test_export_duplicates_selected_meshes_and_cleans_temporary_objects(tmp_path: Path) -> None:
    bpy = pytest.importorskip("bpy")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("box_mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("box", mesh)
    bpy.context.scene.collection.objects.link(obj)

    target = tmp_path / "box.glb"
    assert ModelIOMixin().export_model(["box"], str(target), y_up=True) == str(target)
    assert target.exists() and target.stat().st_size > 0
    assert not [o for o in bpy.data.objects if o.name.startswith("__forge3d_export__")]
