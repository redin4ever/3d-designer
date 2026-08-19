"""Managed material texture library.

This module is deliberately independent from Blender and the web application. It owns
texture metadata, validation, managed-file copying, and stable serialization.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Mapping, Sequence

SUPPORTED_CHANNELS = ("albedo", "normal", "roughness", "metallic")
SUPPORTED_COLOR_SPACES = {
    "albedo": "sRGB",
    "normal": "Non-Color",
    "roughness": "Non-Color",
    "metallic": "Non-Color",
}
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGE_BYTES = 32 * 1024 * 1024
BUILTIN_PRESETS = ("wood", "brick", "concrete", "stone", "metal", "plaster")


@dataclass(frozen=True, slots=True)
class TextureTransform:
    repeat: tuple[float, float] = (1.0, 1.0)
    rotation: float = 0.0
    offset: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        if len(self.repeat) != 2 or any(not math.isfinite(value) or value <= 0 for value in self.repeat):
            raise ValueError("texture repeat values must be finite and greater than zero")
        if not math.isfinite(self.rotation):
            raise ValueError("texture rotation must be finite")
        if len(self.offset) != 2 or any(not math.isfinite(value) for value in self.offset):
            raise ValueError("texture offset values must be finite")


@dataclass(frozen=True, slots=True)
class TextureMap:
    channel: str
    path: str
    color_space: str


@dataclass(frozen=True, slots=True)
class MaterialTexture:
    name: str
    maps: tuple[TextureMap, ...]
    transform: TextureTransform = TextureTransform()
    builtin: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "builtin": self.builtin,
            "maps": [
                {"channel": item.channel, "path": item.path, "color_space": item.color_space}
                for item in self.maps
            ],
            "transform": {
                "repeat": list(self.transform.repeat),
                "rotation": self.transform.rotation,
                "offset": list(self.transform.offset),
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "MaterialTexture":
        transform_value = value.get("transform", {})
        if not isinstance(transform_value, Mapping):
            raise ValueError("material transform must be an object")
        maps_value = value.get("maps", [])
        if not isinstance(maps_value, Sequence) or isinstance(maps_value, (str, bytes)):
            raise ValueError("material maps must be an array")
        maps = tuple(
            TextureMap(
                channel=str(item["channel"]),
                path=str(item["path"]),
                color_space=str(item["color_space"]),
            )
            for item in maps_value
        )
        return cls(
            name=str(value["name"]),
            maps=maps,
            transform=TextureTransform(
                repeat=tuple(transform_value.get("repeat", (1.0, 1.0))),
                rotation=float(transform_value.get("rotation", 0.0)),
                offset=tuple(transform_value.get("offset", (0.0, 0.0))),
            ),
            builtin=bool(value.get("builtin", False)),
        )


class TextureLibrary:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def list_presets(self) -> tuple[str, ...]:
        return BUILTIN_PRESETS

    def list_materials(self) -> tuple[MaterialTexture, ...]:
        custom = []
        if self.root.is_dir():
            for manifest in sorted(self.root.glob("*/material.json")):
                try:
                    custom.append(self.get(manifest.parent.name))
                except (KeyError, ValueError):
                    continue
        return tuple(self._builtin(name) for name in BUILTIN_PRESETS) + tuple(custom)

    def create(self, name: str, source_maps: Mapping[str, Path | str], *, transform: TextureTransform | None = None) -> MaterialTexture:
        self._validate_name(name)
        if name in BUILTIN_PRESETS or (self.root / name).exists():
            raise ValueError(f"texture material already exists: {name}")
        material = self._copy_material(name, source_maps, transform or TextureTransform(), builtin=False)
        self._write_material(material)
        return material

    def get(self, name: str) -> MaterialTexture:
        self._validate_name(name)
        if name in BUILTIN_PRESETS:
            return self._builtin(name)
        manifest = self.root / name / "material.json"
        if not manifest.is_file():
            raise KeyError(f"unknown texture material: {name}")
        try:
            return MaterialTexture.from_dict(json.loads(manifest.read_text(encoding="utf-8")))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid texture material manifest: {name}") from exc

    def update(self, name: str, source_maps: Mapping[str, Path | str], *, transform: TextureTransform | None = None) -> MaterialTexture:
        self._validate_name(name)
        if name in BUILTIN_PRESETS:
            raise ValueError("built-in texture presets cannot be updated")
        if not (self.root / name / "material.json").is_file():
            raise KeyError(f"unknown texture material: {name}")
        material = self._copy_material(name, source_maps, transform or self.get(name).transform, builtin=False)
        self._write_material(material, replace=True)
        return material

    def apply(self, name: str, object_ids: Sequence[str]) -> dict[str, object]:
        self.get(name)
        ids = list(object_ids)
        if not ids or any(not isinstance(object_id, str) or not object_id for object_id in ids):
            raise ValueError("at least one non-empty object id is required")
        return {"material": name, "object_ids": ids}

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
            raise ValueError("texture material name must be 1-64 safe characters")

    @staticmethod
    def _builtin(name: str) -> MaterialTexture:
        maps = tuple(
            TextureMap(channel, f"builtin://{name}/{channel}", SUPPORTED_COLOR_SPACES[channel])
            for channel in SUPPORTED_CHANNELS
        )
        return MaterialTexture(name=name, maps=maps, builtin=True)

    def _copy_material(
        self,
        name: str,
        source_maps: Mapping[str, Path | str],
        transform: TextureTransform,
        *,
        builtin: bool,
    ) -> MaterialTexture:
        if not source_maps or any(channel not in SUPPORTED_CHANNELS for channel in source_maps):
            raise ValueError(f"texture maps must use only {SUPPORTED_CHANNELS}")
        validated: list[tuple[str, Path]] = []
        for channel in SUPPORTED_CHANNELS:
            if channel not in source_maps:
                continue
            source = Path(source_maps[channel])
            suffix = source.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                raise ValueError("texture image format is not supported; use PNG, JPEG, or WebP")
            if not source.is_file():
                raise ValueError(f"texture image does not exist: {source}")
            if source.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("texture image exceeds the 32 MB limit")
            validated.append((channel, source))
        self._pending_sources = tuple(validated)
        maps = tuple(
            TextureMap(channel, f"{name}/{channel}{source.suffix.lower()}", SUPPORTED_COLOR_SPACES[channel])
            for channel, source in validated
        )
        return MaterialTexture(name=name, maps=maps, transform=transform, builtin=builtin)

    def _write_material(self, material: MaterialTexture, *, replace: bool = False) -> None:
        target = self.root / material.name
        temporary = self.root / f".{material.name}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            for item in material.maps:
                source = next(
                    path for channel, path in getattr(self, "_pending_sources", ()) if channel == item.channel
                ) if getattr(self, "_pending_sources", ()) else None
                if source is not None:
                    destination = temporary / Path(item.path).name
                    shutil.copy2(source, destination)
            (temporary / "material.json").write_text(
                json.dumps(material.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if target.exists():
                if not replace:
                    raise ValueError(f"texture material already exists: {material.name}")
                shutil.rmtree(target)
            temporary.rename(target)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        finally:
            self._pending_sources = ()
