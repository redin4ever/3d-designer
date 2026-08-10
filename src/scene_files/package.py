"""Portable, content-addressed ``.forge3d`` ZIP packages.

The package layer deliberately stops before replay.  ``Scene.load`` reconstructs the
document and target ledger without touching the engine; the caller can validate the
returned scene and choose when to restore/replay it into a prepared engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from scene import Scene
from scene.geometry_snapshot import capture, is_geometry_snapshot
from importing import IMPORT_OPERATION_KIND

from . import (
    MissingDependencyError,
    PackageError,
    PackageLoadResult,
    PackageManifest,
    PackageSaveResult,
    PackageValidationResult,
)

PACKAGE_VERSION = 1
_DOCUMENT_ENTRY = "scene/document.json"
_CURRENT_ENTRY = "geometry/current.json"
_SOURCE_KEYS = {"path", "filepath", "file_path", "source_path", "asset_path", "source"}
_TEXTURE_KEYS = {"path", "filepath", "file_path", "source_path"}


@dataclass(frozen=True, slots=True)
class _Asset:
    entry: str
    digest: str
    original: str
    kind: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_entry(name: str) -> bool:
    """Return whether a ZIP member is a relative, POSIX package path."""
    if not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and path != PurePosixPath(".")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8")


def _read_json(raw: bytes, label: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{label} is not valid UTF-8 JSON: {exc}"


def _existing_path(raw: str) -> Path | None:
    if raw.startswith(("assets/", "geometry/", "scene/")):
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path = path.resolve(strict=True)
    except OSError:
        return None
    return path if path.is_file() else None


def _rewrite(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite(item, replacements) for item in value)
    if isinstance(value, str):
        return replacements.get(value, replacements.get(str(Path(value)), value))
    return value


def _iter_strings(value: Any, keys: set[str], parent_key: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item:
                yield item
            yield from _iter_strings(item, keys, key)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item, keys, parent_key)


def _path_replacement(
    raw: str,
    *,
    kind: str,
    assets_by_digest: dict[str, _Asset],
    assets: list[_Asset],
    missing: list[str],
) -> str:
    source = _existing_path(raw)
    if source is None:
        missing.append(raw)
        return raw
    try:
        data = source.read_bytes()
    except OSError:
        missing.append(raw)
        return raw
    digest = _sha256(data)
    asset = assets_by_digest.get(digest)
    if asset is None:
        suffix = source.suffix.lower() if source.suffix and source.suffix.isalnum() else ".bin"
        asset = _Asset(f"assets/{kind}/{digest}{suffix}", digest, raw, kind)
        assets_by_digest[digest] = asset
        assets.append(asset)
    return asset.entry


def _manifest_from_dict(data: dict[str, Any]) -> PackageManifest:
    dependencies: list[dict[str, str]] = []
    for item in data.get("dependencies", []):
        if isinstance(item, str):
            dependencies.append({"entry": item, "sha256": ""})
        elif isinstance(item, dict):
            dependencies.append(
                {
                    "entry": str(item.get("entry", "")),
                    "sha256": str(item.get("sha256", "")),
                }
            )
    barriers = {
        str(key): str(value)
        for key, value in (data.get("barrier_geometry", {}) or {}).items()
    }
    return PackageManifest(
        format=str(data.get("format", "")),
        version=data.get("version"),
        entries=tuple(str(item) for item in data.get("entries", []) or []),
        dependencies=tuple(
            (item["entry"], item["sha256"]) for item in dependencies
        ),
        document_entry=str(data.get("document", _DOCUMENT_ENTRY)),
        current_geometry=str(data.get("current_geometry", _CURRENT_ENTRY)),
        barrier_geometry=tuple(sorted(barriers.items())),
    )


def _legacy_result(path: Path) -> PackageValidationResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return PackageValidationResult(False, errors=(f"legacy scene JSON is invalid: {exc}",))
    if not isinstance(data, dict) or not isinstance(data.get("schema_version"), int):
        return PackageValidationResult(False, errors=("file is neither a forge3d package nor a legacy scene JSON",))
    return PackageValidationResult(
        True,
        warnings=("legacy plain scene JSON loaded; resave is recommended as .forge3d",),
        legacy=True,
    )


def _open_archive(path: Path) -> tuple[zipfile.ZipFile | None, PackageValidationResult | None]:
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        return None, PackageValidationResult(False, errors=(f"invalid forge3d ZIP: {exc}",))
    names = [info.filename for info in archive.infolist()]
    errors: list[str] = []
    if len(names) != len(set(names)):
        errors.append("archive contains duplicate ZIP entries")
    for name in names:
        if not _safe_entry(name):
            errors.append(f"path traversal or unsafe archive entry: {name!r}")
    if errors:
        archive.close()
        return None, PackageValidationResult(False, errors=tuple(errors))
    return archive, None


def validate_package(path: str | Path) -> PackageValidationResult:
    """Validate a package completely without extracting or touching an engine."""
    source = Path(path)
    if source.suffix.lower() != ".forge3d":
        return _legacy_result(source)
    archive, early = _open_archive(source)
    if early is not None:
        return early
    assert archive is not None
    try:
        if "manifest.json" not in archive.namelist():
            return PackageValidationResult(False, errors=("manifest.json is missing",))
        manifest_data, error = _read_json(archive.read("manifest.json"), "manifest.json")
        if error:
            return PackageValidationResult(False, errors=(error,))
        if not isinstance(manifest_data, dict):
            return PackageValidationResult(False, errors=("manifest.json must contain an object",))
        manifest = _manifest_from_dict(manifest_data)
        if manifest.format != "forge3d":
            return PackageValidationResult(False, manifest=manifest, errors=("manifest format is not forge3d",))
        if not isinstance(manifest.version, int):
            return PackageValidationResult(False, manifest=manifest, errors=("manifest version is not an integer",))
        if manifest.version > PACKAGE_VERSION:
            return PackageValidationResult(False, manifest=manifest, errors=(f"manifest version {manifest.version} is newer than supported version {PACKAGE_VERSION}",))
        names = set(archive.namelist())
        errors = []
        required = {"manifest.json", manifest.document_entry, manifest.current_geometry}
        required.update(entry for _, entry in manifest.barrier_geometry)
        required.update(manifest.entries)
        for entry in sorted(required):
            if not _safe_entry(entry):
                errors.append(f"path traversal or unsafe manifest entry: {entry!r}")
            elif entry not in names:
                errors.append(f"manifest entry is missing: {entry}")
        missing: list[str] = []
        for entry, digest in manifest.dependencies:
            if entry and not _safe_entry(entry):
                errors.append(f"path traversal or unsafe dependency entry: {entry!r}")
                continue
            if not entry or entry not in names:
                missing.append(entry or "<unnamed dependency>")
                continue
            if digest and _sha256(archive.read(entry)) != digest:
                errors.append(f"dependency hash mismatch: {entry}")
        for label, entry in (("document", manifest.document_entry), ("current geometry", manifest.current_geometry)):
            if entry in names:
                payload, parse_error = _read_json(archive.read(entry), entry)
                if parse_error:
                    errors.append(parse_error)
                elif label == "current geometry" and not isinstance(payload, dict):
                    errors.append(f"{entry} must contain an object")
        if manifest.current_geometry in names:
            temp = Path(tempfile.mkdtemp(prefix="forge3d-validate-")) / "current.json"
            try:
                temp.write_bytes(archive.read(manifest.current_geometry))
                if not is_geometry_snapshot(str(temp)):
                    errors.append(f"{manifest.current_geometry} is not a geometry snapshot")
            finally:
                shutil.rmtree(temp.parent, ignore_errors=True)
        return PackageValidationResult(
            not errors and not missing,
            manifest=manifest,
            errors=tuple(errors),
            missing_dependencies=tuple(sorted(set(missing))),
        )
    finally:
        archive.close()


def _extract(archive: zipfile.ZipFile, root: Path, entries: Iterable[str]) -> None:
    for name in entries:
        if not _safe_entry(name):
            raise PackageError(f"path traversal or unsafe archive entry: {name!r}")
        target = root / Path(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))


def _rewrite_extracted_document(document: dict[str, Any], root: Path, manifest: PackageManifest) -> Path:
    replacements: dict[str, str] = {}
    for _, entry in manifest.dependencies:
        replacements[entry] = str(root / Path(*PurePosixPath(entry).parts))
    for index, entry in manifest.barrier_geometry:
        replacements[entry] = str(root / Path(*PurePosixPath(entry).parts))
        replacements[str(index)] = replacements.get(str(index), str(index))
    document = _rewrite(document, replacements)
    states = document.get("geometry_states")
    if isinstance(states, dict):
        for key, entry in manifest.barrier_geometry:
            if key in states:
                states[key] = str(root / Path(*PurePosixPath(entry).parts))
    barriers = document.get("barriers")
    if isinstance(barriers, list):
        by_index = dict(manifest.barrier_geometry)
        for barrier in barriers:
            if isinstance(barrier, dict):
                index = str(barrier.get("index", ""))
                if index in by_index:
                    barrier["snapshot_path"] = str(root / Path(*PurePosixPath(by_index[index]).parts))
    output = root / _DOCUMENT_ENTRY
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_json_bytes(document))
    return output


def load_package(
    path: str | Path,
    engine: Any,
    handlers: Any,
    *,
    extraction_root: str | Path | None = None,
) -> PackageLoadResult:
    """Validate and prepare a package; never replay or mutate ``engine``."""
    source = Path(path)
    validation = validate_package(source)
    if not validation.valid:
        return PackageLoadResult(validation=validation)
    root = Path(extraction_root) if extraction_root is not None else Path(tempfile.mkdtemp(prefix="forge3d-package-"))
    root.mkdir(parents=True, exist_ok=True)
    if validation.legacy:
        document_path = root / _DOCUMENT_ENTRY
        document_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, document_path)
        try:
            prepared = Scene.load(str(document_path), engine, handlers)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return PackageLoadResult(
                PackageValidationResult(False, errors=(f"legacy scene document is invalid: {exc}",), warnings=validation.warnings),
                extraction_root=root,
            )
        return PackageLoadResult(validation, prepared, root, None, ())

    assert validation.manifest is not None
    archive, early = _open_archive(source)
    if early is not None or archive is None:
        return PackageLoadResult(early or PackageValidationResult(False, errors=("cannot open package",)))
    try:
        _extract(archive, root, validation.manifest.entries or archive.namelist())
        document_data, error = _read_json(archive.read(validation.manifest.document_entry), validation.manifest.document_entry)
        if error or not isinstance(document_data, dict):
            return PackageLoadResult(PackageValidationResult(False, errors=(error or "scene document must be an object",), manifest=validation.manifest), extraction_root=root)
        document_path = _rewrite_extracted_document(document_data, root, validation.manifest)
        try:
            prepared = Scene.load(str(document_path), engine, handlers)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return PackageLoadResult(PackageValidationResult(False, errors=(f"scene document is invalid: {exc}",), manifest=validation.manifest), extraction_root=root)
        current = root / Path(*PurePosixPath(validation.manifest.current_geometry).parts)
        barriers = tuple(
            (int(index), root / Path(*PurePosixPath(entry).parts))
            for index, entry in validation.manifest.barrier_geometry
        )
        return PackageLoadResult(validation, prepared, root, current, barriers)
    finally:
        archive.close()


def save_scene(scene: Any, path: str | Path) -> PackageSaveResult:
    """Write a self-contained package atomically, collecting all missing dependencies."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    assets: list[_Asset] = []
    assets_by_digest: dict[str, _Asset] = {}
    missing: list[str] = []
    with tempfile.TemporaryDirectory(prefix="forge3d-package-save-") as workspace_name:
        workspace = Path(workspace_name)
        document_path = workspace / "document.json"
        scene.save(str(document_path))
        document = json.loads(document_path.read_text(encoding="utf-8"))
        replacements: dict[str, str] = {}
        for operation in document.get("operations", []):
            if operation.get("kind") not in {IMPORT_OPERATION_KIND, "import_model"}:
                continue
            for raw in _iter_strings(operation.get("params", {}), _SOURCE_KEYS):
                entry = _path_replacement(raw, kind="sources", assets_by_digest=assets_by_digest, assets=assets, missing=missing)
                replacements[raw] = entry
                replacements[str(Path(raw))] = entry
        current_path = workspace / "current.json"
        capture(scene.engine, str(current_path))
        snapshot_paths: dict[str, Path] = {}
        for index, raw_path in getattr(scene, "_snapshots").to_json().items():
            source = Path(raw_path)
            if not source.is_file():
                missing.append(raw_path)
                continue
            destination = workspace / "barriers" / f"{int(index)}.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            snapshot_paths[index] = destination
        snapshot_files = [current_path, *snapshot_paths.values()]
        for snapshot_path in snapshot_files:
            try:
                snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PackageError(f"geometry snapshot is invalid: {snapshot_path}: {exc}") from exc
            for raw in _iter_strings(snapshot_data, _TEXTURE_KEYS):
                if _existing_path(raw) is None and not raw.startswith("assets/"):
                    missing.append(raw)
                    continue
                if raw.startswith("assets/"):
                    continue
                entry = _path_replacement(raw, kind="textures", assets_by_digest=assets_by_digest, assets=assets, missing=missing)
                replacements[raw] = entry
            snapshot_path.write_bytes(_json_bytes(_rewrite(snapshot_data, replacements)))
        document = _rewrite(document, replacements)
        geometry_states = document.get("geometry_states")
        barrier_entries: dict[str, str] = {}
        if isinstance(geometry_states, dict):
            for index, snapshot_path in snapshot_paths.items():
                entry = f"geometry/barriers/{int(index)}.json"
                barrier_entries[index] = entry
                geometry_states[index] = entry
        for barrier in document.get("barriers", []):
            if isinstance(barrier, dict) and str(barrier.get("index")) in barrier_entries:
                barrier["snapshot_path"] = barrier_entries[str(barrier["index"])]
        if missing:
            unique_missing = tuple(sorted(set(missing)))
            raise MissingDependencyError(unique_missing)
        document_bytes = _json_bytes(document)
        package_entries = ["manifest.json", _DOCUMENT_ENTRY, _CURRENT_ENTRY]
        package_entries.extend(sorted(barrier_entries.values()))
        package_entries.extend(asset.entry for asset in assets)
        manifest = {
            "format": "forge3d",
            "version": PACKAGE_VERSION,
            "document": _DOCUMENT_ENTRY,
            "current_geometry": _CURRENT_ENTRY,
            "barrier_geometry": barrier_entries,
            "entries": package_entries,
            "dependencies": [
                {"entry": asset.entry, "sha256": asset.digest, "kind": asset.kind, "source": asset.original}
                for asset in assets
            ],
            "content_addressing": "sha256",
        }
        manifest_bytes = _json_bytes(manifest)
        temp_target = target.with_name(target.name + ".tmp")
        try:
            with zipfile.ZipFile(temp_target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", manifest_bytes)
                archive.writestr(_DOCUMENT_ENTRY, document_bytes)
                archive.writestr(_CURRENT_ENTRY, current_path.read_bytes())
                for index, entry in sorted(barrier_entries.items(), key=lambda item: int(item[0])):
                    archive.writestr(entry, snapshot_paths[index].read_bytes())
                for asset in assets:
                    original = _existing_path(asset.original)
                    if original is not None:
                        archive.writestr(asset.entry, original.read_bytes())
            os.replace(temp_target, target)
        finally:
            if temp_target.exists():
                temp_target.unlink()
        return PackageSaveResult(target, tuple(package_entries))
