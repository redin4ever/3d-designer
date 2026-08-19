from __future__ import annotations

from pathlib import Path

import pytest

from app.texture_assets import TextureAssetError, resolve_texture_asset


def _write(root: Path, material: str, filename: str, data: bytes = b"texture") -> Path:
    directory = root / material
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("albedo.png", "image/png"), ("albedo.jpg", "image/jpeg"),
     ("albedo.jpeg", "image/jpeg"), ("albedo.webp", "image/webp")],
)
def test_resolves_allowlisted_asset_with_response_metadata(tmp_path: Path, filename: str, content_type: str):
    path = _write(tmp_path, "wood", filename)

    asset = resolve_texture_asset(tmp_path, "wood", filename)

    assert asset.path == path
    assert asset.content_type == content_type
    assert asset.headers == {
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=31536000, immutable",
    }


@pytest.mark.parametrize(
    ("material", "filename"),
    [
        ("../outside", "albedo.png"),
        ("wood/other", "albedo.png"),
        ("wood", "../outside.png"),
        ("wood", "nested/albedo.png"),
        ("wood", "..\\outside.png"),
        ("wood", "%2e%2e%2foutside.png"),
        ("wood", "albedo.png?download=1"),
        ("wood?x=1", "albedo.png"),
        ("wood", "albedo.png#fragment"),
        ("C:\\outside", "albedo.png"),
        ("wood", "C:\\outside.png"),
    ],
)
def test_rejects_traversal_absolute_paths_and_query_tricks(tmp_path: Path, material: str, filename: str):
    with pytest.raises(TextureAssetError):
        resolve_texture_asset(tmp_path, material, filename)


@pytest.mark.parametrize("filename", ["albedo.gif", "albedo.svg", "albedo", "albedo.PNG.exe"])
def test_rejects_unrecognized_extensions(tmp_path: Path, filename: str):
    _write(tmp_path, "wood", filename)

    with pytest.raises(TextureAssetError):
        resolve_texture_asset(tmp_path, "wood", filename)


def test_rejects_missing_directories_and_non_files(tmp_path: Path):
    (tmp_path / "wood" / "albedo.png").parent.mkdir(parents=True)
    (tmp_path / "wood" / "directory.png").mkdir()

    with pytest.raises(TextureAssetError):
        resolve_texture_asset(tmp_path, "missing", "albedo.png")
    with pytest.raises(TextureAssetError):
        resolve_texture_asset(tmp_path, "wood", "missing.png")
    with pytest.raises(TextureAssetError):
        resolve_texture_asset(tmp_path, "wood", "directory.png")


def test_rejects_symlink_that_escapes_managed_root(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
    outside.write_bytes(b"outside")
    link = tmp_path / "wood"
    link.mkdir()
    try:
        (link / "escape.png").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this Windows test environment")

    with pytest.raises(TextureAssetError):
        resolve_texture_asset(tmp_path, "wood", "escape.png")


def test_allows_a_symlink_that_stays_inside_managed_root(tmp_path: Path):
    original = _write(tmp_path, "wood", "original.png")
    try:
        (tmp_path / "wood" / "alias.png").symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this Windows test environment")

    asset = resolve_texture_asset(tmp_path, "wood", "alias.png")

    assert asset.path == original.resolve()
