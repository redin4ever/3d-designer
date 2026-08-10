"""RED integration tests for scene-file reachability through the live product."""

from __future__ import annotations

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
