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


@dataclass(frozen=True, slots=True)
class PackageLoadResult:
    validation: PackageValidationResult
    scene: Any = None
    extraction_root: Path | None = None


class PackageError(ValueError):
    pass


class MissingDependencyError(PackageError):
    def __init__(self, paths: tuple[str, ...]):
        self.paths = paths
        super().__init__("missing dependencies: " + ", ".join(paths))


def save_scene(scene: Any, path: str | Path) -> PackageSaveResult:
    raise NotImplementedError


def validate_package(path: str | Path) -> PackageValidationResult:
    raise NotImplementedError


def load_package(
    path: str | Path,
    engine: Any,
    handlers: Any,
    *,
    extraction_root: str | Path | None = None,
) -> PackageLoadResult:
    raise NotImplementedError


__all__ = [
    "MissingDependencyError",
    "PackageError",
    "PackageLoadResult",
    "PackageSaveResult",
    "PackageValidationResult",
    "load_package",
    "save_scene",
    "validate_package",
]
