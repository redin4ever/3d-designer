"""Replayable texture-material operations built on :mod:`textures.library`.

The library owns files and material metadata; this module owns the operation boundary and
connects those definitions to whatever engine implementation is supplied by the caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from contracts import EngineProtocol, Operation, OperationResult, ToolError, ToolRole, ToolSpec
from textures import MaterialTexture, TextureLibrary, TextureTransform

__all__ = [
    "TEXTURE_MATERIAL_SPECS",
    "create_texture_material",
    "update_texture_material",
    "apply_texture_material",
]


def _error(rule: str, detail: str, suggestion: str) -> ToolError:
    return ToolError(rule=rule, detail=detail, suggestion=suggestion)


def _text(params: Mapping[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _error(
            "ops.missing_parameter",
            f"{name} is required and must be a non-empty string",
            f"pass {name} as a string",
        )
    return value.strip()


def _root(params: Mapping[str, Any]) -> Path:
    value = params.get("managed_root")
    return Path(value) if isinstance(value, str) and value.strip() else Path.cwd() / ".forge3d" / "textures"


def _maps(params: Mapping[str, Any]) -> dict[str, str]:
    value = params.get("maps", params.get("source_maps"))
    if not isinstance(value, Mapping) or not value:
        raise _error(
            "ops.missing_parameter",
            "maps is required and must contain at least one texture channel",
            "pass maps such as {'albedo': 'wall.png'}",
        )
    return {str(channel): str(path) for channel, path in value.items()}


def _pair(params: Mapping[str, Any], name: str, default: tuple[float, float]) -> tuple[float, float]:
    value = params.get(name, default)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise _error("ops.invalid_parameter_value", f"{name} must be [x, y]", "pass two finite numbers")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise _error("ops.invalid_parameter_value", f"{name} must contain numbers", "pass two finite numbers") from exc


def _transform(params: Mapping[str, Any], fallback: TextureTransform | None = None) -> TextureTransform:
    base = fallback or TextureTransform()
    try:
        return TextureTransform(
            repeat=_pair(params, "repeat", base.repeat),
            rotation=float(params.get("rotation", base.rotation)),
            offset=_pair(params, "offset", base.offset),
        )
    except (TypeError, ValueError) as exc:
        raise _error("ops.invalid_parameter_value", f"invalid texture transform: {exc}", "use finite repeat, rotation, and offset values") from exc


def _library(params: Mapping[str, Any]) -> tuple[TextureLibrary, str]:
    name = params.get("name") or params.get("preset") or params.get("material_id")
    if not isinstance(name, str) or not name.strip():
        raise _error("ops.missing_parameter", "name or preset is required", "choose a texture material")
    return TextureLibrary(_root(params)), name.strip()


def _library_failure(exc: Exception) -> ToolError:
    if isinstance(exc, KeyError):
        rule = "ops.unknown_texture_material"
    else:
        rule = "ops.invalid_texture_material"
    return _error(rule, str(exc), "check the material name, image paths, and supported file formats")


def _engine_material(engine: EngineProtocol, material: MaterialTexture) -> None:
    """Create or update a native material when the engine exposes the basic contract."""
    if callable(getattr(engine, "create_texture_material", None)):
        try:
            engine.create_texture_material(material)
            return
        except TypeError:
            pass

    create = getattr(engine, "create_material", None)
    if not callable(create):
        raise _error("ops.engine_capability", "engine cannot create materials", "use an engine with material support")
    try:
        if material.name not in getattr(engine, "_materials", {}):
            create(material.name, (0.8, 0.8, 0.8))
        set_pbr = getattr(engine, "set_pbr", None)
        if callable(set_pbr):
            set_pbr(material.name, roughness=0.5, metallic=1.0 if material.name == "metal" else 0.0)
    except Exception as exc:
        if isinstance(exc, ToolError):
            raise
        raise _error("ops.engine_material_failed", str(exc), "check the connected engine material backend") from exc


def _assign(engine: EngineProtocol, object_id: str, material: MaterialTexture, slot: int) -> None:
    assign_texture = getattr(engine, "assign_texture_material", None)
    if callable(assign_texture):
        try:
            assign_texture(object_id, material.name, slot, material)
        except TypeError:
            try:
                assign_texture(object_id, material.name, slot)
            except Exception as exc:
                raise _error("ops.engine_material_failed", str(exc), "check the connected engine material backend") from exc
        except Exception as exc:
            raise _error("ops.engine_material_failed", str(exc), "check the connected engine material backend") from exc
        return
    try:
        engine.assign_material(object_id, material.name, slot)
    except Exception as exc:
        raise _error("ops.engine_material_failed", str(exc), "check the connected engine material backend") from exc


def create_texture_material(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Copy validated local maps into managed storage and create the native material."""
    library, name = _library(op.params)
    try:
        material = library.create(name, _maps(op.params), transform=_transform(op.params))
        _engine_material(engine, material)
    except ToolError:
        raise
    except Exception as exc:
        raise _library_failure(exc) from exc
    return OperationResult(op_id=op.op_id, ok=True)


def update_texture_material(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Replace a user material's managed maps and refresh its native material."""
    library, name = _library(op.params)
    try:
        previous = library.get(name)
        material = library.update(name, _maps(op.params), transform=_transform(op.params, previous.transform))
        _engine_material(engine, material)
    except ToolError:
        raise
    except Exception as exc:
        raise _library_failure(exc) from exc
    return OperationResult(op_id=op.op_id, ok=True)


def apply_texture_material(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Apply one material to every selected object after validating the entire request."""
    library, name = _library(op.params)
    raw_ids = op.params.get("object_ids")
    if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)) or not raw_ids:
        raise _error("ops.missing_parameter", "object_ids must contain at least one object id", "pass object_ids as an array")
    object_ids = tuple(raw_ids)
    if any(not isinstance(object_id, str) or not object_id for object_id in object_ids):
        raise _error("ops.invalid_parameter_value", "object_ids must contain non-empty strings", "reselect the parts to texture")
    try:
        slot = int(op.params.get("slot", 0))
    except (TypeError, ValueError) as exc:
        raise _error("ops.invalid_parameter_value", "slot must be a non-negative integer", "pass slot=0 or another material slot") from exc
    if slot < 0:
        raise _error("ops.invalid_parameter_value", "slot must be non-negative", "pass slot=0 or another material slot")
    try:
        material = library.get(name)
    except Exception as exc:
        raise _library_failure(exc) from exc

    snapshots = []
    for object_id in object_ids:
        if not engine.exists(object_id):
            raise _error("ops.unknown_object", f"no object named {object_id!r}", "reselect the part and try again")
        try:
            snapshots.append(engine.snapshot(object_id))
        except Exception as exc:
            raise _error("ops.unknown_object", str(exc), "reselect the part and try again") from exc

    _engine_material(engine, material)
    for object_id, snapshot in zip(object_ids, snapshots):
        if snapshot.uvs is None:
            try:
                engine.unwrap(object_id)
            except Exception as exc:
                raise _error("ops.uv_unwrap_failed", str(exc), "unwrap the part before applying a texture") from exc
    for object_id in object_ids:
        _assign(engine, object_id, material, slot)
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=object_ids)


_TEXTURE_ROLES = (ToolRole.BLOCKOUT, ToolRole.REFINE, ToolRole.DETAIL, ToolRole.POLISH)
TEXTURE_MATERIAL_SPECS = (
    ToolSpec(
        name="create_texture_material",
        description="Create a reusable managed texture material from local PNG, JPEG, or WebP maps.",
        roles=_TEXTURE_ROLES,
        input_schema={"type": "object", "properties": {"name": {"type": "string"}, "managed_root": {"type": "string"}, "maps": {"type": "object"}, "repeat": {"type": "array"}, "rotation": {"type": "number"}, "offset": {"type": "array"}},
        "required": ["name", "managed_root", "maps"], "additionalProperties": False},
        mutating=True,
    ),
    ToolSpec(
        name="update_texture_material",
        description="Update a reusable managed texture material from local image maps.",
        roles=_TEXTURE_ROLES,
        input_schema={"type": "object", "properties": {"name": {"type": "string"}, "managed_root": {"type": "string"}, "maps": {"type": "object"}, "repeat": {"type": "array"}, "rotation": {"type": "number"}, "offset": {"type": "array"}},
        "required": ["name", "managed_root", "maps"], "additionalProperties": False},
        mutating=True,
    ),
    ToolSpec(
        name="apply_texture_material",
        description="Apply a managed texture material to one or more selected objects, auto-unwrapping missing UVs.",
        roles=_TEXTURE_ROLES,
        input_schema={"type": "object", "properties": {"name": {"type": "string"}, "managed_root": {"type": "string"}, "object_ids": {"type": "array"}, "slot": {"type": "integer", "minimum": 0}},
        "required": ["object_ids"], "additionalProperties": True},
        mutating=True,
    ),
)
