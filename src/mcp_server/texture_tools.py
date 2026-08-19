"""Read-only discovery for the managed texture material library."""

from __future__ import annotations

from pathlib import Path

from textures import TextureLibrary

__all__ = ["list_texture_materials"]


def list_texture_materials(managed_root: str = "") -> dict[str, object]:
    root = Path(managed_root) if managed_root else Path.cwd() / ".forge3d" / "textures"
    materials = TextureLibrary(root).list_materials()
    return {"managed_root": str(root), "materials": [material.to_dict() for material in materials]}
