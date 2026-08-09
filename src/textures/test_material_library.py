from __future__ import annotations

import json
from pathlib import Path

import pytest

from textures import (
    BUILTIN_PRESETS,
    MAX_IMAGE_BYTES,
    SUPPORTED_CHANNELS,
    SUPPORTED_COLOR_SPACES,
    TextureLibrary,
    TextureTransform,
)


def _image(path: Path, size: int = 8) -> Path:
    path.write_bytes(b"image" * size)
    return path


def test_builtin_presets_include_starter_materials(tmp_path: Path) -> None:
    library = TextureLibrary(tmp_path)
    assert library.list_presets() == BUILTIN_PRESETS
    assert set(BUILTIN_PRESETS) >= {"wood", "brick", "concrete", "stone", "metal", "plaster"}
    assert all(library.get(name).builtin for name in BUILTIN_PRESETS)


def test_four_channels_have_declared_color_spaces_and_roundtrip(tmp_path: Path) -> None:
    library = TextureLibrary(tmp_path)
    maps = {channel: _image(tmp_path / f"{channel}.png") for channel in SUPPORTED_CHANNELS}
    material = library.create("paint", maps)
    assert tuple(item.channel for item in material.maps) == SUPPORTED_CHANNELS
    assert {item.channel: item.color_space for item in material.maps} == SUPPORTED_COLOR_SPACES
    restored = library.get("paint")
    assert restored == material
    assert json.loads(json.dumps(material.to_dict())) == restored.to_dict()


def test_transform_validates_repeat_rotation_and_offset(tmp_path: Path) -> None:
    library = TextureLibrary(tmp_path)
    source = {"albedo": _image(tmp_path / "albedo.jpg")}
    material = library.create(
        "repeatable",
        source,
        transform=TextureTransform(repeat=(2.5, 3.0), rotation=45.0, offset=(0.25, -0.5)),
    )
    assert material.transform == TextureTransform((2.5, 3.0), 45.0, (0.25, -0.5))
    with pytest.raises(ValueError):
        library.create("zero-repeat", source, transform=TextureTransform(repeat=(0, 1)))
    with pytest.raises(ValueError):
        library.create("bad-offset", source, transform=TextureTransform(offset=(float("nan"), 0)))


@pytest.mark.parametrize("extension", [".png", ".jpg", ".jpeg", ".webp"])
def test_supported_image_formats_are_accepted(tmp_path: Path, extension: str) -> None:
    library = TextureLibrary(tmp_path / "managed")
    material = library.create("format", {"albedo": _image(tmp_path / f"source{extension}")})
    assert material.maps[0].path.startswith("format/")


def test_invalid_format_and_oversized_image_are_rejected_atomically(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    library = TextureLibrary(root)
    bad = _image(tmp_path / "source.gif")
    with pytest.raises(ValueError, match="supported"):
        library.create("bad-format", {"albedo": bad})
    assert not (root / "bad-format").exists()

    huge = tmp_path / "huge.png"
    with huge.open("wb") as handle:
        handle.truncate(MAX_IMAGE_BYTES + 1)
    with pytest.raises(ValueError, match="32 MB"):
        library.create("too-large", {"albedo": huge})
    assert not (root / "too-large").exists()


def test_missing_channel_or_file_rejects_without_partial_copy(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    library = TextureLibrary(root)
    valid = _image(tmp_path / "valid.png")
    with pytest.raises(ValueError):
        library.create("atomic", {"albedo": valid, "normal": tmp_path / "missing.png"})
    assert not (root / "atomic").exists()


def test_update_and_apply_are_serialized_and_copy_into_managed_directory(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    library = TextureLibrary(root)
    first = library.create("wall", {"albedo": _image(tmp_path / "one.webp")})
    assert (root / first.maps[0].path).is_file()
    updated = library.update("wall", {"albedo": _image(tmp_path / "two.png")})
    assert updated != first
    assert (root / updated.maps[0].path).is_file()
    assignment = library.apply("wall", ["part-a", "part-b"])
    assert assignment == {"material": "wall", "object_ids": ["part-a", "part-b"]}
