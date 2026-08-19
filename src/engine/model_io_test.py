from __future__ import annotations

from pathlib import Path

import pytest

import contracts
from contracts import EngineError
from engine.model_io import ModelIOMixin, export_operator_for_suffix, import_operator_for_suffix


def test_dispatch_covers_every_interchange_model_extension() -> None:
    export_extensions = getattr(contracts, "SUPPORTED_MODEL_EXPORT_EXTENSIONS", ())
    import_extensions = getattr(contracts, "SUPPORTED_MODEL_IMPORT_EXTENSIONS", ())
    assert set(export_extensions) == {
        ".glb", ".gltf", ".fbx", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc",
    }
    assert set(import_extensions) == {*export_extensions, ".blend"}
    for suffix in export_extensions:
        assert import_operator_for_suffix(suffix)
        assert export_operator_for_suffix(suffix)


@pytest.mark.parametrize("path", ["missing.obj", "mesh.txt"])
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
def test_blend_import_appends_editable_meshes_without_replacing_scene(tmp_path: Path) -> None:
    bpy = pytest.importorskip("bpy")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    source_mesh = bpy.data.meshes.new("library_mesh")
    source_mesh.from_pydata([(0, 0, 0), (2, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    source_obj = bpy.data.objects.new("library_part", source_mesh)
    camera_data = bpy.data.cameras.new("library_camera_data")
    camera_obj = bpy.data.objects.new("library_camera", camera_data)
    target = tmp_path / "parts.blend"
    bpy.data.libraries.write(str(target), {source_obj, source_mesh, camera_obj, camera_data})
    bpy.data.objects.remove(source_obj, do_unlink=True)
    bpy.data.objects.remove(camera_obj, do_unlink=True)

    sentinel_mesh = bpy.data.meshes.new("sentinel_mesh")
    sentinel_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    sentinel = bpy.data.objects.new("sentinel", sentinel_mesh)
    bpy.context.scene.collection.objects.link(sentinel)

    result = ModelIOMixin().import_model(str(target), flatten=False)

    assert "sentinel" in bpy.data.objects
    assert result.object_ids == ("library_part",)
    appended = bpy.data.objects[result.object_ids[0]]
    assert appended in bpy.context.scene.objects.values()
    assert appended.library is None
    assert appended.data.library is None
    assert any("library_camera" in warning for warning in result.warnings)


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
