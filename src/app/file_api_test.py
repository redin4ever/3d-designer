"""Contract tests for the framework-neutral live file job service."""

from __future__ import annotations

import threading
import time
import json
from pathlib import Path

import pytest

from app.file_api import FileApiError, FileJobManager, FileOperationResult, OwnerThreadDispatcher


def _eventually(manager: FileJobManager, job_id: str, status: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = manager.get(job_id)
        if result["status"] == status:
            return result
        time.sleep(0.01)
    pytest.fail(f"job {job_id} did not reach {status!r}: {manager.get(job_id)!r}")


def test_accepts_binary_job_completes_and_exposes_one_download(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def export(context):
        seen["input"] = context.source_path
        context.report(0.5, "writing")
        return FileOperationResult(
            data=b"glTF fixture",
            filename="scene.glb",
            content_type="model/gltf-binary",
            format="glb",
        )

    manager = FileJobManager(tmp_path, operations={"export-model": export})
    started = manager.submit(
        {"content-type": "application/json"},
        b'{"action":"export-model","format":"glb","scope":"scene"}',
    )

    assert started["status"] == "queued"
    result = _eventually(manager, started["job_id"], "complete")
    assert result["progress"] == 1.0
    assert result["filename"] == "scene.glb"
    assert result["download_url"] == f"/api/file-io/downloads/{result['download_token']}"

    body, filename, content_type = manager.read_download(result["download_token"])
    assert (body, filename, content_type) == (b"glTF fixture", "scene.glb", "model/gltf-binary")
    assert Path(seen["input"]).is_dir()
    manager.close()


def test_operation_failure_is_structured_in_status(tmp_path: Path) -> None:
    def fail(_context):
        raise ValueError("bad model")

    manager = FileJobManager(tmp_path, operations={"import-model": fail})
    started = manager.submit(
        {"content-type": "model/obj", "x-forge3d-action": "import-model", "x-forge3d-filename": "part.obj"},
        b"solid part",
    )
    result = _eventually(manager, started["job_id"], "failed")

    assert result["ok"] is False
    assert result["error"]["code"] == "operation_failed"
    assert "bad model" in result["error"]["message"]
    manager.close()


def test_binary_import_carries_advanced_axis_and_unit_overrides(tmp_path: Path) -> None:
    seen = {}

    def import_model(context):
        seen.update(context.payload)

    manager = FileJobManager(tmp_path, operations={"import-model": import_model})
    started = manager.submit(
        {
            "content-type": "model/obj",
            "x-forge3d-action": "import-model",
            "x-forge3d-filename": "part.obj",
            "x-forge3d-source-up": "Y",
            "x-forge3d-unit-scale": "0.01",
            "x-forge3d-flatten": "false",
        },
        b"v 0 0 0\n",
    )

    assert _eventually(manager, started["job_id"], "complete")
    assert seen == {"source_up": "Y", "unit_scale": 0.01, "flatten": False}
    manager.close()


def test_rejects_oversize_and_non_local_binary_requests(tmp_path: Path) -> None:
    manager = FileJobManager(tmp_path, max_upload_bytes=4)

    with pytest.raises(FileApiError) as oversize:
        manager.submit(
            {"content-type": "model/obj", "x-forge3d-action": "import-model", "x-forge3d-filename": "part.obj"},
            b"12345",
        )
    assert oversize.value.status == 413
    assert oversize.value.payload["error"]["code"] == "upload_too_large"

    remote_manager = FileJobManager(tmp_path / "remote")
    with pytest.raises(FileApiError) as remote:
        remote_manager.submit(
            {"content-type": "application/json"},
            b'{"action":"import-model","url":"https://example.invalid/part.obj"}',
        )
    assert remote.value.status == 400
    assert remote.value.payload["error"]["code"] == "local_file_required"
    remote_manager.close()
    manager.close()


def test_cancel_stops_a_running_job_and_is_idempotent(tmp_path: Path) -> None:
    started = threading.Event()

    def long_operation(context):
        started.set()
        while not context.cancel_event.is_set():
            time.sleep(0.005)
        return {"message": "worker observed cancellation"}

    manager = FileJobManager(tmp_path, operations={"import-model": long_operation})
    job = manager.submit(
        {"content-type": "model/obj", "x-forge3d-action": "import-model", "x-forge3d-filename": "part.obj"},
        b"solid part",
    )
    assert started.wait(1)
    cancelling = manager.cancel(job["job_id"])
    assert cancelling["status"] in {"cancelling", "cancelled"}
    assert manager.cancel(job["job_id"])["status"] in {"cancelling", "cancelled"}
    assert _eventually(manager, job["job_id"], "cancelled")["message"]
    manager.close()


def test_unknown_jobs_and_download_tokens_are_safe_errors(tmp_path: Path) -> None:
    manager = FileJobManager(tmp_path)

    with pytest.raises(FileApiError) as unknown:
        manager.get("missing")
    assert unknown.value.status == 404
    assert unknown.value.payload["error"]["code"] == "unknown_job"

    with pytest.raises(FileApiError) as token:
        manager.read_download("../../outside")
    assert token.value.status == 404
    assert token.value.payload["error"]["code"] == "unknown_download"
    manager.close()


def test_filenames_are_deterministic_and_download_paths_are_confined(tmp_path: Path) -> None:
    def export(context):
        return FileOperationResult(data=b"x", filename=context.filename)

    manager = FileJobManager(tmp_path, operations={"export-model": export})
    first = manager.submit(
        {"content-type": "application/json"},
        json.dumps({"action": "export-model", "filename": "..\\..\\bad name?.glb"}).encode(),
    )
    result = _eventually(manager, first["job_id"], "complete")
    path = manager.download_path(result["download_token"])
    assert path.is_relative_to((tmp_path / "downloads").resolve())
    assert path.name == "bad_name_.glb"
    assert ".." not in path.parts

    outside = tmp_path.parent / "outside.glb"
    outside.write_bytes(b"outside")
    with pytest.raises(FileApiError) as confined:
        manager.register_download(outside, "outside.glb", "application/octet-stream")
    assert confined.value.payload["error"]["code"] == "download_path_forbidden"
    outside.unlink()
    manager.close()


def test_cleanup_removes_job_files_and_tokens(tmp_path: Path) -> None:
    seen: dict[str, Path] = {}

    def export(context):
        seen["source_root"] = context.source_path
        return FileOperationResult(data=b"x", filename="scene.glb")

    manager = FileJobManager(
        tmp_path,
        operations={"export-model": export},
    )
    job = manager.submit({"content-type": "application/json"}, b'{"action":"export-model"}')
    result = _eventually(manager, job["job_id"], "complete")
    source_root = seen["source_root"]
    output = manager.download_path(result["download_token"])

    manager.cleanup(job["job_id"])

    assert not source_root.exists()
    assert not output.exists()
    with pytest.raises(FileApiError):
        manager.get(job["job_id"])
    with pytest.raises(FileApiError):
        manager.read_download(result["download_token"])
    manager.close()


def test_operation_runner_marshals_engine_callbacks_to_the_owner_thread(tmp_path: Path) -> None:
    owner_thread = threading.get_ident()
    dispatcher = OwnerThreadDispatcher()
    callback_threads: list[int] = []

    def export(_context):
        callback_threads.append(threading.get_ident())
        return FileOperationResult(data=b"glb", filename="scene.glb")

    manager = FileJobManager(
        tmp_path,
        operations={"export-model": export},
        operation_runner=dispatcher.call,
    )
    started = manager.submit(
        {"content-type": "application/json"},
        b'{"action":"export-model","format":"glb"}',
    )

    deadline = time.monotonic() + 2
    result = manager.get(started["job_id"])
    while result["status"] not in {"complete", "failed", "cancelled"}:
        dispatcher.drain()
        if time.monotonic() > deadline:
            pytest.fail(f"owner-thread job did not finish: {result!r}")
        time.sleep(0.005)
        result = manager.get(started["job_id"])

    assert result["status"] == "complete", result
    assert callback_threads == [owner_thread]
    manager.close()
    dispatcher.close()
