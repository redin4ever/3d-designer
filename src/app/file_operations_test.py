"""End-to-end tests for the callbacks bound behind browser file jobs."""

from __future__ import annotations

import json
import time
import zipfile
from types import MethodType

from app import build_app
from app.file_api import FileJobManager
from contracts import Vec3


def _complete(manager: FileJobManager, started: dict, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(started["job_id"])
        if job["status"] in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"file job did not finish: {manager.get(started['job_id'])}")


def test_live_callbacks_save_import_and_export_the_current_scene(tmp_path) -> None:
    from app.file_operations import build_file_operations

    app = build_app(prefer_blender=False, attach_viewer=False)
    app.engine.create_primitive("cube", "cube", Vec3(1, 1, 1))
    app.orchestrator.pause()

    original_export = app.engine.export_model

    def writing_export(self, object_ids, path, **kwargs):
        original_export(object_ids, path, **kwargs)
        with open(path, "wb") as handle:
            handle.write(b"model")
        return path

    app.engine.export_model = MethodType(writing_export, app.engine)
    manager = FileJobManager(tmp_path / "jobs", operations=build_file_operations(app))

    saved = _complete(
        manager,
        manager.submit(
            {"content-type": "application/json"},
            b'{"action":"save-project","filename":"house.forge3d"}',
        ),
    )
    assert saved["status"] == "complete"
    project, _, _ = manager.read_download(saved["download_token"])
    project_path = tmp_path / "house.forge3d"
    project_path.write_bytes(project)
    assert zipfile.is_zipfile(project_path)

    live_scene = app.scene
    app.engine.create_primitive("later", "cube", Vec3(1, 1, 1))
    opened = _complete(
        manager,
        manager.submit(
            {
                "content-type": "application/vnd.forge3d+zip",
                "x-forge3d-action": "open-project",
                "x-forge3d-filename": "house.forge3d",
            },
            project,
        ),
    )
    assert opened["status"] == "complete"
    assert app.scene is live_scene
    assert tuple(app.engine.list_objects()) == ("cube",)

    imported = _complete(
        manager,
        manager.submit(
            {
                "content-type": "model/obj",
                "x-forge3d-action": "import-model",
                "x-forge3d-filename": "chair.obj",
            },
            b"v 0 0 0\n",
        ),
    )
    assert imported["status"] == "complete"
    assert app.scene.document.operations[-1].opaque is True

    exported = _complete(
        manager,
        manager.submit(
            {"content-type": "application/json"},
            json.dumps(
                {
                    "action": "export-model",
                    "format": "obj",
                    "profile": "generic",
                    "scope": "selection",
                    "object_ids": ["cube"],
                }
            ).encode(),
        ),
    )
    assert exported["status"] == "complete"
    assert manager.read_download(exported["download_token"])[0] == b"model"
    manager.close()


def test_import_pauses_an_active_run_and_leaves_it_paused_for_inspection(tmp_path) -> None:
    from app.file_operations import build_file_operations

    app = build_app(prefer_blender=False, attach_viewer=False)
    manager = FileJobManager(tmp_path, operations=build_file_operations(app))
    result = _complete(
        manager,
        manager.submit(
            {
                "content-type": "model/obj",
                "x-forge3d-action": "import-model",
                "x-forge3d-filename": "chair.obj",
            },
            b"v 0 0 0\n",
        ),
    )

    assert result["status"] == "complete", result
    assert app.orchestrator.state.value == "paused"
    assert app.scene.document.operations[-1].opaque is True
    manager.close()
