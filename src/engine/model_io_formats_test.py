"""Real Blender smoke coverage for every advertised export format."""

from __future__ import annotations

import pytest

import contracts
from engine.model_io import ModelIOMixin


@pytest.mark.needs_blender
@pytest.mark.parametrize(
    "suffix",
    getattr(contracts, "SUPPORTED_MODEL_EXPORT_EXTENSIONS", contracts.SUPPORTED_MODEL_EXTENSIONS),
)
def test_every_advertised_format_writes_a_real_file(tmp_path, suffix: str) -> None:
    """Advertising a format that reaches Blender with wrong operator options is a broken export."""
    bpy = pytest.importorskip("bpy")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("format_mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("format_triangle", mesh)
    bpy.context.scene.collection.objects.link(obj)
    target = tmp_path / f"triangle{suffix}"

    ModelIOMixin().export_model([obj.name], str(target), y_up=True)

    assert target.is_file()
    assert target.stat().st_size > 0
    assert not [item for item in bpy.data.objects if item.name.startswith("__forge3d_export__")]
