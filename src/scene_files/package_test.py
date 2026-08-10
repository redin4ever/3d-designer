"""RED tests for the portable ``.forge3d`` project package."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from contracts import Operation, Vec3
from scene import Scene
from scene_files import (
    MissingDependencyError,
    load_package,
    save_scene,
    validate_package,
)
from testing import FakeEngine


def _scene_with_geometry() -> Scene:
    engine = FakeEngine()
    engine.create_mesh("cube", [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)], [(0, 1, 2)])
    return Scene(engine, {}, scene_id="package-test")


def _write_zip(path: Path, entries: dict[str, object]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in entries.items():
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            archive.writestr(name, raw)


def test_save_contains_manifest_document_current_geometry_and_barrier_snapshots(tmp_path):
    """A project must carry the log and geometry needed to open it without temp files."""
    scene = _scene_with_geometry()
    path = tmp_path / "house.forge3d"

    result = save_scene(scene, path)

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert {"manifest.json", "scene/document.json", "geometry/current.json"} <= names
    assert manifest["format"] == "forge3d"
    assert result.path == path


def test_save_deduplicates_identical_source_and_texture_assets(tmp_path):
    """Identical referenced bytes must occupy one content-addressed managed entry."""
    source = tmp_path / "source.obj"
    texture = tmp_path / "map.png"
    source.write_bytes(b"same-bytes")
    texture.write_bytes(b"same-bytes")
    scene = _scene_with_geometry()
    scene.document.operations.append(
        Operation("import", "import_model", {"path": str(source)})
    )
    scene.document.head = 1
    scene.engine.snapshot("cube")
    # The material definition is placed in the current geometry snapshot by the package.
    scene.engine.create_texture_material(type("Material", (), {"name": "mat", "to_dict": lambda self: {"name": "mat", "maps": [{"channel": "albedo", "path": str(texture)}]}})())
    path = tmp_path / "dedupe.forge3d"

    save_scene(scene, path)

    with zipfile.ZipFile(path) as archive:
        assets = [name for name in archive.namelist() if name.startswith("assets/")]
    assert len(assets) == 1


def test_validate_rejects_zip_traversal(tmp_path):
    """A crafted archive must not escape the extraction directory."""
    path = tmp_path / "evil.forge3d"
    _write_zip(path, {"../escape": b"owned"})

    result = validate_package(path)

    assert not result.valid
    assert any("traversal" in error for error in result.errors)


def test_save_reports_all_missing_dependencies_atomically(tmp_path):
    """One bad source must report every missing dependency before writing a package."""
    scene = _scene_with_geometry()
    scene.document.operations.extend(
        [
            Operation("one", "import_model", {"path": str(tmp_path / "one.obj")}),
            Operation("two", "import_model", {"path": str(tmp_path / "two.obj")}),
        ]
    )
    scene.document.head = 2
    target = tmp_path / "missing.forge3d"

    with pytest.raises(MissingDependencyError) as exc:
        save_scene(scene, target)

    assert {"one.obj", "two.obj"} <= set(exc.value.paths)
    assert not target.exists()


def test_legacy_plain_scene_json_load_reports_resave_recommendation(tmp_path):
    """Existing JSON projects remain readable while clearly asking for the portable format."""
    scene = _scene_with_geometry()
    legacy = tmp_path / "legacy.json"
    scene.save(str(legacy))

    result = validate_package(legacy)

    assert result.valid
    assert any("resave" in warning.lower() for warning in result.warnings)


def test_validate_rejects_corrupt_and_newer_manifests(tmp_path):
    """Corrupt or future package metadata must fail before any scene is prepared."""
    corrupt = tmp_path / "corrupt.forge3d"
    _write_zip(corrupt, {"manifest.json": b"{"})
    future = tmp_path / "future.forge3d"
    _write_zip(future, {"manifest.json": {"format": "forge3d", "version": 999}})

    assert not validate_package(corrupt).valid
    assert not validate_package(future).valid
    assert any("newer" in error for error in validate_package(future).errors)


def test_load_validation_failure_does_not_mutate_live_engine(tmp_path):
    """A dependency failure must leave the prepared live engine exactly untouched."""
    scene = _scene_with_geometry()
    package = tmp_path / "broken.forge3d"
    _write_zip(
        package,
        {
            "manifest.json": {
                "format": "forge3d",
                "version": 1,
                "entries": ["manifest.json", "scene/document.json", "geometry/current.json"],
                "dependencies": ["assets/sources/missing.obj"],
            },
            "scene/document.json": {},
            "geometry/current.json": {},
        },
    )
    before = tuple(scene.engine.list_objects())

    result = load_package(package, scene.engine, {})

    assert not result.validation.valid
    assert tuple(scene.engine.list_objects()) == before
