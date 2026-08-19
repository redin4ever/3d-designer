"""RED integration tests for scene-file reachability through the live product."""

from __future__ import annotations

import time

from contracts import ToolRole


def test_model_file_operations_reach_the_concrete_engine_and_handler_graph() -> None:
    from app import build_handlers
    from engine.session import BlenderEngine
    from importing import IMPORT_OPERATION_KIND
    from mcp_server import build_registry

    assert callable(getattr(BlenderEngine, "import_model", None))
    assert callable(getattr(BlenderEngine, "export_model", None))
    assert IMPORT_OPERATION_KIND in build_handlers(include_raw=False)

    import_roles = {
        role
        for role, specs in build_registry(include_raw=False).items()
        if any(spec.name == IMPORT_OPERATION_KIND for spec in specs)
    }
    assert import_roles == {
        ToolRole.BLOCKOUT,
        ToolRole.REFINE,
        ToolRole.DETAIL,
        ToolRole.POLISH,
    }


def test_agent_import_is_recorded_as_one_opaque_undo_step(tmp_path) -> None:
    from app import build_app
    from importing import IMPORT_OPERATION_KIND
    from mcp_server import dispatch

    source = tmp_path / "house.obj"
    source.write_text("v 0 0 0\n", encoding="utf-8")
    app = build_app(prefer_blender=False, include_raw=False, attach_viewer=False)
    lease = app.orchestrator.acquire("integration-luna", app.orchestrator.phase)

    result = dispatch(
        IMPORT_OPERATION_KIND,
        {"path": str(source)},
        orchestrator=app.orchestrator,
        lease=lease,
    )

    assert result["ok"] is True
    assert app.scene.document.head == 1
    operation = app.scene.document.operations[0]
    assert operation.kind == IMPORT_OPERATION_KIND
    assert operation.opaque is True
    assert len(app.scene.document.barriers) == 1


def test_live_http_routes_create_poll_and_download_a_project_job(tmp_path) -> None:
    """The browser controller's same-origin endpoints must reach the live App, not 404."""
    import json
    import socket
    import time
    import urllib.request
    import zipfile

    from app import build_app
    from app.live import FRONTEND_DIR, serve_frontend

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = build_app(prefer_blender=False, attach_viewer=False)
    server = serve_frontend(port, FRONTEND_DIR, app)
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/file-io/jobs",
            data=b'{"action":"save-project","filename":"live.forge3d"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            started = json.load(response)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/file-io/jobs/{started['job_id']}",
                timeout=5,
            ) as response:
                status = json.load(response)
            if status["status"] in {"complete", "failed"}:
                break
            time.sleep(0.01)
        assert status["status"] == "complete", status
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{status['download_url']}", timeout=5
        ) as response:
            project = response.read()
        target = tmp_path / "live.forge3d"
        target.write_bytes(project)
        assert zipfile.is_zipfile(target)
    finally:
        server.shutdown()
        server.server_close()


def test_real_blender_glb_job_round_trips_on_the_engine_owner_thread(tmp_path) -> None:
    """The live regression: a worker-thread bpy export has no active-object context."""
    import pytest

    pytest.importorskip("bpy")
    from app import build_app
    from app.file_api import FileJobManager, OwnerThreadDispatcher
    from app.file_operations import build_file_operations
    from contracts import Vec3

    app = build_app(prefer_blender=True, attach_viewer=False)
    app.engine.reset()
    app.engine.create_primitive("roundtrip_cube", "cube", Vec3(1, 1, 1))
    app.orchestrator.pause()
    dispatcher = OwnerThreadDispatcher()
    manager = FileJobManager(
        tmp_path / "real-jobs",
        operations=build_file_operations(app),
        operation_runner=dispatcher.call,
    )
    try:
        started = manager.submit(
            {"content-type": "application/json"},
            b'{"action":"export-model","format":"glb","scope":"scene"}',
        )
        deadline = time.monotonic() + 15
        result = manager.get(started["job_id"])
        while result["status"] not in {"complete", "failed", "cancelled"}:
            dispatcher.drain()
            if time.monotonic() > deadline:
                raise AssertionError(f"real GLB job did not finish: {result!r}")
            time.sleep(0.005)
            result = manager.get(started["job_id"])

        assert result["status"] == "complete", result
        glb, filename, content_type = manager.read_download(result["download_token"])
        assert filename.endswith(".glb")
        assert content_type == "model/gltf-binary"
        assert len(glb) > 100

        source = tmp_path / "roundtrip.glb"
        source.write_bytes(glb)
        app.engine.reset()
        imported = app.engine.import_model(str(source))
        assert imported.object_ids
        assert set(imported.object_ids).issubset(set(app.engine.list_objects()))
    finally:
        manager.close()
        dispatcher.close()
        app.engine.reset()
