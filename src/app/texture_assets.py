"""Safe resolution of managed texture files for the live HTTP server.

The live server should only expose files that were copied into its configured texture
directory.  This module deliberately accepts URL path *segments*, rather than a path
string, so traversal and query syntax cannot be interpreted by a filesystem resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from os import PathLike

__all__ = ["TextureAsset", "TextureAssetError", "resolve_texture_asset"]

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_CACHE_CONTROL = "public, max-age=31536000, immutable"


class TextureAssetError(ValueError):
    """Raised when a requested texture is not a safe managed asset."""


@dataclass(frozen=True)
class TextureAsset:
    """Resolved file and headers a live handler can pass to a response."""

    path: Path
    content_type: str
    cache_control: str = _CACHE_CONTROL

    @property
    def headers(self) -> dict[str, str]:
        """HTTP headers for the asset response, excluding length (the server can add it)."""
        return {
            "Content-Type": self.content_type,
            "Cache-Control": self.cache_control,
        }


def _validate_segment(value: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise TextureAssetError(f"invalid texture {label}")
    if any(marker in value for marker in ("/", "\\", "?", "#", "%", "\x00", ":")):
        raise TextureAssetError(f"invalid texture {label}")
    if value in {".", ".."} or PureWindowsPath(value).is_absolute():
        raise TextureAssetError(f"invalid texture {label}")


def resolve_texture_asset(
    managed_root: str | PathLike[str], material: str, filename: str
) -> TextureAsset:
    """Resolve one allowlisted image below ``managed_root``.

    ``material`` and ``filename`` are each one URL segment.  The returned path is the
    resolved filesystem path, so an in-root symlink is harmless while a symlink that
    escapes the managed directory is rejected.
    """
    _validate_segment(material, "material name")
    _validate_segment(filename, "filename")

    suffix = Path(filename).suffix.lower()
    content_type = _CONTENT_TYPES.get(suffix)
    if content_type is None:
        raise TextureAssetError("texture format is not supported; use PNG, JPEG, or WebP")

    try:
        root = Path(managed_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as exc:
        raise TextureAssetError("managed texture directory is unavailable") from exc
    if not root.is_dir():
        raise TextureAssetError("managed texture directory is unavailable")

    candidate = root / material / filename
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TextureAssetError("texture asset was not found") from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise TextureAssetError("texture asset is outside the managed directory") from exc
    if not resolved.is_file():
        raise TextureAssetError("texture asset is not a file")

    return TextureAsset(path=resolved, content_type=content_type)
