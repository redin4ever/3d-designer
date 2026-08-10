"""RED tests for the portable ``.forge3d`` project package."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from contracts import Operation, Vec3
from scene import Scene
from scene.geometry_snapshot import capture
from scene_files import (
    MissingDependencyError,
    load_package,
    save_scene,
    validate_package,
)
from testing import FakeEngine
from textures import MaterialTexture, TextureMap


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


def test_save_packages_each_undo_barrier_geometry_state(tmp_path):
    """Undo barriers must keep both sides of their geometry state in the portable file."""
    scene = _scene_with_geometry()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    capture(scene.engine, str(before))
    capture(scene.engine, str(after))
    scene._snapshots.register(0, str(before), str(after))

    save_scene(scene, tmp_path / "barriers.forge3d")

    with zipfile.ZipFile(tmp_path / "barriers.forge3d") as archive:
        assert "geometry/barriers/0.json" in archive.namelist()
        assert "geometry/barriers/1.json" in archive.namelist()


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
    material = MaterialTexture("mat", (TextureMap("albedo", str(texture), "sRGB"),))
    scene.engine.assign_texture_material("cube", "mat", material=material)
    path = tmp_path / "dedupe.forge3d"

    save_scene(scene, path)

    with zipfile.ZipFile(path) as archive:
        assets = [name for name in archive.namelist() if name.startswith("assets/")]
    assert len(assets) == 1


def test_save_embeds_sources_from_the_registered_import_operation(tmp_path):
    """Packaging follows the operation kind exposed to the editor and agents."""
    from importing import IMPORT_OPERATION_KIND

    source = tmp_path / "registered.obj"
    source.write_text("v 0 0 0\n", encoding="utf-8")
    scene = _scene_with_geometry()
    scene.document.operations.append(
        Operation("registered-import", IMPORT_OPERATION_KIND, {"path": str(source)})
    )
    scene.document.head = 1
    target = tmp_path / "registered.forge3d"

    save_scene(scene, target)

    with zipfile.ZipFile(target) as archive:
        document = json.loads(archive.read("scene/document.json"))
        saved_path = document["operations"][0]["params"]["path"]
        assert saved_path.startswith("assets/sources/")
        assert saved_path in archive.namelist()


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

    assert any(path.endswith("one.obj") for path in exc.value.paths)
    assert any(path.endswith("two.obj") for path in exc.value.paths)
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


def test_valid_load_prepares_scene_without_replaying_into_live_engine(tmp_path):
    """Validation and extraction may prepare a document, but replay remains an explicit commit."""
    source = tmp_path / "model.obj"
    source.write_bytes(b"mesh")
    scene = _scene_with_geometry()
    scene.document.operations.append(Operation("import", "import_model", {"path": str(source)}))
    scene.document.head = 1
    package = tmp_path / "valid.forge3d"
    save_scene(scene, package)
    target_engine = FakeEngine()

    result = load_package(package, target_engine, {})

    assert result.validation.valid
    assert result.scene is not None
    assert tuple(target_engine.list_objects()) == ()
    assert result.current_geometry_path is not None
