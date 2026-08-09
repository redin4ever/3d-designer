"""Managed material texture library.

This module is deliberately independent from Blender and the web application. It owns
texture metadata, validation, managed-file copying, and stable serialization.
"""

from __future__ import annotations

from dataclasses import dataclass
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


class TextureLibrary:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def list_presets(self) -> tuple[str, ...]:
        return BUILTIN_PRESETS

    def create(self, name: str, source_maps: Mapping[str, Path | str], *, transform: TextureTransform | None = None) -> MaterialTexture:
        raise NotImplementedError

    def get(self, name: str) -> MaterialTexture:
        raise NotImplementedError

    def update(self, name: str, source_maps: Mapping[str, Path | str], *, transform: TextureTransform | None = None) -> MaterialTexture:
        raise NotImplementedError

    def apply(self, name: str, object_ids: Sequence[str]) -> dict[str, object]:
        raise NotImplementedError
