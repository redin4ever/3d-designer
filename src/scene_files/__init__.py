"""Portable ``.forge3d`` scene-file packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PackageSaveResult:
    path: Path
    entries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PackageValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()
    missing_dependencies: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    manifest: "PackageManifest | None" = None
    legacy: bool = False


@dataclass(frozen=True, slots=True)
class PackageManifest:
    format: str
    version: Any
    entries: tuple[str, ...]
    dependencies: tuple[tuple[str, str], ...]
    document_entry: str
    current_geometry: str
    barrier_geometry: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PackageLoadResult:
    validation: PackageValidationResult
    scene: Any = None
    extraction_root: Path | None = None
    current_geometry_path: Path | None = None
    barrier_geometry_paths: tuple[tuple[int, Path], ...] = ()


class PackageError(ValueError):
    pass


class MissingDependencyError(PackageError):
    def __init__(self, paths: tuple[str, ...]):
        self.paths = paths
        super().__init__("missing dependencies: " + ", ".join(paths))


def save_scene(scene: Any, path: str | Path) -> PackageSaveResult:
    from .package import save_scene as _save_scene

    return _save_scene(scene, path)


def validate_package(path: str | Path) -> PackageValidationResult:
    from .package import validate_package as _validate_package

    return _validate_package(path)


def load_package(
    path: str | Path,
    engine: Any,
    handlers: Any,
    *,
    extraction_root: str | Path | None = None,
) -> PackageLoadResult:
    from .package import load_package as _load_package

    return _load_package(path, engine, handlers, extraction_root=extraction_root)


__all__ = [
    "MissingDependencyError",
    "PackageError",
    "PackageManifest",
    "PackageLoadResult",
    "PackageSaveResult",
    "PackageValidationResult",
    "load_package",
    "save_scene",
    "validate_package",
]
