from __future__ import annotations

from pathlib import Path

import pytest

from src.engine.texture_materials import (
    TextureMaterialError,
    apply_to_blender,
    export_settings,
    node_plan,
)
from src.textures.library import MaterialTexture, TextureMap, TextureTransform


def material(*maps: tuple[str, str, str], builtin: bool = False) -> MaterialTexture:
    return MaterialTexture(
        name="test",
        maps=tuple(TextureMap(channel, path, color_space) for channel, path, color_space in maps),
        transform=TextureTransform(repeat=(2.0, 3.0), rotation=0.25, offset=(0.1, -0.2)),
        builtin=builtin,
    )


def test_node_plan_connects_channels_and_preserves_transform() -> None:
    plan = node_plan(
        "wall",
        material(
            ("albedo", "wall/albedo.png", "sRGB"),
            ("normal", "wall/normal.png", "Non-Color"),
            ("roughness", "wall/roughness.webp", "Non-Color"),
            ("metallic", "wall/metallic.jpg", "Non-Color"),
        ),
    )

    assert plan.material_id == "wall"
    assert plan.mapping == {"repeat": (2.0, 3.0), "rotation": 0.25, "offset": (0.1, -0.2)}
    assert {node["channel"] for node in plan.nodes if node["kind"] == "image"} == {
        "albedo", "normal", "roughness", "metallic"
    }
    assert ("albedo", "Color", "Principled BSDF", "Base Color") in plan.links
    assert ("normal", "Color", "Normal Map", "Color") in plan.links
    assert ("Normal Map", "Normal", "Principled BSDF", "Normal") in plan.links
    assert ("roughness", "Color", "Principled BSDF", "Roughness") in plan.links
    assert ("metallic", "Color", "Principled BSDF", "Metallic") in plan.links


def test_node_plan_uses_deterministic_procedural_nodes_for_builtins() -> None:
    plan = node_plan("wood", material(builtin=True))

    assert plan.nodes
    assert all(node["kind"] != "image" for node in plan.nodes)
    assert plan.nodes == node_plan("wood", material(builtin=True)).nodes
    assert any(node["kind"] == "builtin" and node["preset"] == "wood" for node in plan.nodes)


@pytest.mark.parametrize(
    "channel,color_space",
    [("albedo", "Non-Color"), ("normal", "sRGB"), ("roughness", "sRGB"), ("metallic", "sRGB")],
)
def test_node_plan_rejects_wrong_channel_color_space(channel: str, color_space: str) -> None:
    with pytest.raises(TextureMaterialError, match="color space"):
        node_plan("bad", material((channel, "x.png", color_space)))


def test_node_plan_rejects_duplicate_or_unsupported_maps() -> None:
    with pytest.raises(TextureMaterialError, match="duplicate"):
        node_plan("bad", material(("albedo", "a.png", "sRGB"), ("albedo", "b.png", "sRGB")))
    with pytest.raises(TextureMaterialError, match="channel"):
        node_plan("bad", material(("emission", "e.png", "sRGB")))


def test_export_settings_are_pure_and_distinguish_gltf_and_glb() -> None:
    assert export_settings(Path("scene.glb")) == {
        "format": "GLB",
        "embed_textures": True,
        "copy_textures": False,
    }
    assert export_settings("scene.gltf") == {
        "format": "GLTF_SEPARATE",
        "embed_textures": False,
        "copy_textures": True,
    }
    with pytest.raises(ValueError, match="\.glb or \.gltf"):
        export_settings("scene.obj")


def test_apply_to_blender_lazily_imports_bpy_and_reuses_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    bpy = _FakeBpy()
    monkeypatch.setitem(__import__("sys").modules, "bpy", bpy)
    target = _FakeMaterial()
    texture = material(("albedo", "wall/albedo.png", "sRGB"))

    assert apply_to_blender("wall", texture, target) is target
    first_nodes = target.node_tree.nodes
    assert any(node.type == "ShaderNodeTexImage" for node in first_nodes)
    assert apply_to_blender("wall", texture, target) is target
    assert len(target.node_tree.nodes) == len(first_nodes)


class _FakeBpy:
    class data:
        class images:
            @staticmethod
            def load(path: str, check_existing: bool = True):
                return object()


class _FakeSocket:
    def __init__(self) -> None:
        self.default_value = None


class _FakeNode:
    def __init__(self, node_type: str) -> None:
        self.type = node_type
        self.name = ""
        self.label = ""
        self.inputs = {name: _FakeSocket() for name in ("Color", "Base Color", "Normal", "Roughness", "Metallic")}
        self.outputs = {name: _FakeSocket() for name in ("Color", "Normal", "BSDF")}


class _FakeNodes(list):
    def new(self, node_type: str):
        node = _FakeNode(node_type)
        self.append(node)
        return node


class _FakeLinks:
    def new(self, output, input_socket) -> None:
        pass


class _FakeTree:
    def __init__(self) -> None:
        self.nodes = _FakeNodes()
        self.links = _FakeLinks()


class _FakeMaterial:
    def __init__(self) -> None:
        self.use_nodes = False
        self.node_tree = _FakeTree()
