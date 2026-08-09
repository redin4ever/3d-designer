"""Blender adapter for the managed texture-material library.

The node plan is deliberately plain Python data.  Blender is imported only by
``apply_to_blender`` so the validation and export policy remain unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any

from src.textures.library import (
    MaterialTexture,
    SUPPORTED_CHANNELS,
    SUPPORTED_COLOR_SPACES,
    TextureMap,
)


class TextureMaterialError(ValueError):
    """Raised when a managed texture cannot be represented by Blender nodes."""


@dataclass(frozen=True, slots=True)
class NodePlan:
    material_id: str
    nodes: tuple[dict[str, object], ...]
    links: tuple[tuple[str, str, str, str], ...]
    mapping: dict[str, object]


_BUILTIN_NODE_TYPES = {
    "wood": "ShaderNodeTexNoise",
    "brick": "ShaderNodeTexBrick",
    "concrete": "ShaderNodeTexNoise",
    "stone": "ShaderNodeTexVoronoi",
    "metal": "ShaderNodeTexNoise",
    "plaster": "ShaderNodeTexNoise",
}


def _validate(texture: MaterialTexture) -> None:
    if not isinstance(texture, MaterialTexture):
        raise TextureMaterialError("material must be a MaterialTexture")
    seen: set[str] = set()
    for item in _maps_for(texture):
        if item.channel not in SUPPORTED_CHANNELS:
            raise TextureMaterialError(f"unsupported texture channel: {item.channel}")
        if item.channel in seen:
            raise TextureMaterialError(f"duplicate texture channel: {item.channel}")
        seen.add(item.channel)
        expected = SUPPORTED_COLOR_SPACES[item.channel]
        if item.color_space != expected:
            raise TextureMaterialError(
                f"texture channel {item.channel} requires {expected} color space"
            )
        if not item.path or not isinstance(item.path, str):
            raise TextureMaterialError(f"texture path for {item.channel} is invalid")
        if not item.path.startswith("builtin://") and Path(item.path).suffix.lower() not in {
            ".png", ".jpg", ".jpeg", ".webp"
        }:
            raise TextureMaterialError("texture paths must use PNG, JPEG, or WebP")
    if texture.builtin and not texture.name:
        raise TextureMaterialError("built-in texture preset needs a name")


def node_plan(material_id: str, texture: MaterialTexture) -> NodePlan:
    """Return the deterministic Blender node graph contract for ``texture``."""

    _validate(texture)
    if not isinstance(material_id, str) or not material_id:
        raise TextureMaterialError("material id must be a non-empty string")

    nodes: list[dict[str, object]] = [
        {"name": "Texture Coordinate", "kind": "texcoord", "type": "ShaderNodeTexCoord"},
        {
            "name": "Texture Mapping",
            "kind": "mapping",
            "type": "ShaderNodeMapping",
            "repeat": texture.transform.repeat,
            "rotation": texture.transform.rotation,
            "offset": texture.transform.offset,
        },
        {"name": "Principled BSDF", "kind": "shader", "type": "ShaderNodeBsdfPrincipled"},
        {"name": "Material Output", "kind": "output", "type": "ShaderNodeOutputMaterial"},
    ]
    links: list[tuple[str, str, str, str]] = [
        ("Texture Coordinate", "Generated", "Texture Mapping", "Vector"),
        ("Principled BSDF", "BSDF", "Material Output", "Surface"),
    ]
    preset_name = material_id if texture.builtin else texture.name
    for item in _maps_for(texture):
        if texture.builtin:
            node_name = f"Builtin {item.channel}"
            nodes.append(
                {
                    "name": node_name,
                    "kind": "builtin",
                    "type": _BUILTIN_NODE_TYPES.get(preset_name, "ShaderNodeTexNoise"),
                    "preset": preset_name,
                    "channel": item.channel,
                    "seed": sum(ord(char) for char in preset_name) + len(item.channel),
                }
            )
        else:
            node_name = f"Texture {item.channel}"
            nodes.append(
                {
                    "name": node_name,
                    "kind": "image",
                    "type": "ShaderNodeTexImage",
                    "channel": item.channel,
                    "path": item.path,
                    "color_space": item.color_space,
                }
            )
        links.append((item.channel, "Color", "Principled BSDF", _socket_for(item.channel)))
        links.append(("Texture Mapping", "Vector", node_name, "Vector"))
        if item.channel == "normal":
            links.pop(-2)
            links.append((item.channel, "Color", "Normal Map", "Color"))
            links.append(("Normal Map", "Normal", "Principled BSDF", "Normal"))
            nodes.append({"name": "Normal Map", "kind": "normal", "type": "ShaderNodeNormalMap"})
    return NodePlan(material_id, tuple(nodes), tuple(links), {
        "repeat": texture.transform.repeat,
        "rotation": texture.transform.rotation,
        "offset": texture.transform.offset,
    })


def _map_type(channel: str, preset: str) -> TextureMap:
    return TextureMap(channel, f"builtin://{preset}/{channel}", SUPPORTED_COLOR_SPACES[channel])


def _maps_for(texture: MaterialTexture) -> tuple[TextureMap, ...]:
    return texture.maps or tuple(_map_type(channel, texture.name) for channel in SUPPORTED_CHANNELS) if texture.builtin else texture.maps


def _socket_for(channel: str) -> str:
    return {
        "albedo": "Base Color",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "normal": "Normal",
    }[channel]


def _node(nodes: Any, node_type: str, name: str) -> Any:
    for item in nodes:
        if getattr(item, "name", "") == name:
            return item
    item = nodes.new(node_type)
    item.name = name
    return item


def _link(tree: Any, output_node: Any, output_socket: str, input_node: Any, input_socket: str) -> None:
    output = getattr(output_node, "outputs", {}).get(output_socket)
    target = getattr(input_node, "inputs", {}).get(input_socket)
    if output is not None and target is not None:
        tree.links.new(output, target)


def apply_to_blender(
    material_id: str,
    texture: MaterialTexture,
    blender_material: Any | None = None,
) -> Any:
    """Apply a managed texture to a bpy material, importing bpy lazily."""

    bpy = importlib.import_module("bpy")
    if blender_material is None:
        blender_material = bpy.data.materials.get(material_id) if hasattr(bpy.data, "materials") else None
    if blender_material is None:
        raise TextureMaterialError(f"Blender material not found: {material_id}")
    plan = node_plan(material_id, texture)
    blender_material.use_nodes = True
    tree = blender_material.node_tree
    nodes = tree.nodes
    created = {entry["name"]: _node(nodes, str(entry["type"]), str(entry["name"])) for entry in plan.nodes}

    mapping = created["Texture Mapping"]
    _set_input(mapping, "Scale", (*texture.transform.repeat, 1.0))
    _set_input(mapping, "Rotation", (0.0, 0.0, texture.transform.rotation))
    _set_input(mapping, "Location", (*texture.transform.offset, 0.0))
    for item in _maps_for(texture):
        image_node = created[f"Texture {item.channel}"] if not texture.builtin else created[f"Builtin {item.channel}"]
        if not texture.builtin:
            image = bpy.data.images.load(item.path, check_existing=True)
            image_node.image = image
            settings = getattr(image, "colorspace_settings", None)
            if settings is not None:
                settings.name = item.color_space
        if item.channel == "normal":
            normal = created["Normal Map"]
            _link(tree, image_node, "Color", normal, "Color")
            _link(tree, normal, "Normal", created["Principled BSDF"], "Normal")
        else:
            _link(tree, image_node, "Color", created["Principled BSDF"], _socket_for(item.channel))
        _link(tree, created["Texture Mapping"], "Vector", image_node, "Vector")
    _link(tree, created["Principled BSDF"], "BSDF", created["Material Output"], "Surface")
    return blender_material


def _set_input(node: Any, name: str, value: object) -> None:
    socket = getattr(node, "inputs", {}).get(name)
    if socket is not None:
        socket.default_value = value


def export_settings(path: str | Path) -> dict[str, object]:
    """Return pure glTF texture packaging settings for an export path."""

    suffix = Path(path).suffix.lower()
    if suffix == ".glb":
        return {"format": "GLB", "embed_textures": True, "copy_textures": False}
    if suffix == ".gltf":
        return {"format": "GLTF_SEPARATE", "embed_textures": False, "copy_textures": True}
    raise ValueError("texture export path must end in .glb or .gltf")
