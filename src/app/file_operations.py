"""Bind framework-neutral file jobs to one live forge3d application."""

from __future__ import annotations

import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from contracts import RunState, SUPPORTED_MODEL_EXTENSIONS
from export import export_scene
from importing import make_import_operation
from scene_files import load_package, save_scene

from .file_api import FileApiError, FileJobContext, FileOperationResult

__all__ = ["build_file_operations"]


def _require_paused(app: Any, action: str) -> None:
    if app.orchestrator.state is not RunState.PAUSED:
        raise FileApiError(
            "run_must_be_paused",
            f"Pause the build before you {action}.",
            status=409,
        )


def _work_path(context: FileJobContext, filename: str) -> Path:
    root = context.output_dir / "work"
    root.mkdir(parents=True, exist_ok=True)
    return root / filename


def _save(app: Any, context: FileJobContext) -> FileOperationResult:
    context.report(0.1, "Packing project history, geometry, and assets.")
    filename = Path(context.filename).with_suffix(".forge3d").name
    target = _work_path(context, filename)
    save_scene(app.scene, target)
    context.report(0.9, "Project package ready.")
    return FileOperationResult(
        path=target,
        filename=filename,
        content_type="application/vnd.forge3d+zip",
        format="forge3d",
        message=f"Saved {filename}.",
    )


def _import(app: Any, context: FileJobContext) -> FileOperationResult:
    _require_paused(app, "import a model")
    context.report(0.1, f"Importing {context.filename}.")
    payload = context.payload
    operation = make_import_operation(
        f"browser-import-{uuid.uuid4().hex[:8]}",
        str(context.source_path),
        source_up=str(payload.get("source_up", "AUTO")),
        unit_scale=float(payload.get("unit_scale", 1.0)),
        flatten=bool(payload.get("flatten", True)),
        phase=app.orchestrator.phase.value,
        author="operator:file-menu",
    )
    report = app.orchestrator.apply_operator_edit(operation)
    if not report.ok:
        raise FileApiError(
            report.error_rule or "import_failed",
            report.error_detail or "The model could not be imported.",
            status=422,
        )
    context.report(1.0, "Model imported.")
    return FileOperationResult(message=f"Imported {context.filename}.")


def _open(app: Any, context: FileJobContext) -> FileOperationResult:
    _require_paused(app, "open a project")
    context.report(0.1, f"Validating {context.filename}.")
    prepared = load_package(
        context.source_path,
        app.engine,
        app.handlers,
        extraction_root=context.output_dir / "opened-project",
    )
    validation = prepared.validation
    if not validation.valid or prepared.scene is None:
        details = [*validation.errors, *validation.missing_dependencies]
        raise FileApiError(
            "project_invalid",
            "; ".join(details) or "The project package is invalid.",
            status=422,
            details=details,
        )
    geometry = str(prepared.current_geometry_path) if prepared.current_geometry_path else ""
    app.scene.replace_with(prepared.scene, geometry)
    app.orchestrator.set_cadence(app.scene.document.check_cadence)
    context.report(1.0, "Project opened.")
    warning = " " + " ".join(validation.warnings) if validation.warnings else ""
    return FileOperationResult(message=f"Opened {context.filename}.{warning}".strip())


def _zip_gltf_outputs(root: Path, filename: str) -> Path:
    archive_path = root / f"{Path(filename).stem}-gltf.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != archive_path:
                archive.write(path, path.relative_to(root).as_posix())
    return archive_path


def _export(app: Any, context: FileJobContext) -> FileOperationResult:
    payload = context.payload
    format_name = str(payload.get("format", "glb")).lower().lstrip(".")
    if f".{format_name}" not in SUPPORTED_MODEL_EXTENSIONS:
        raise FileApiError("unsupported_format", f"Unsupported export format {format_name!r}.")
    requested = payload.get("object_ids") if payload.get("scope") == "selection" else None
    object_ids = tuple(requested or app.engine.list_objects())
    if not object_ids:
        raise FileApiError("nothing_to_export", "There are no scene objects to export.", status=422)
    profile = str(payload.get("profile", "generic"))
    filename = f"{Path(context.filename).stem or 'scene'}.{format_name}"
    target = _work_path(context, filename)
    context.report(0.1, f"Exporting {len(object_ids)} object(s) as {format_name.upper()}.")
    report = export_scene(
        app.engine,
        object_ids,
        str(target),
        profile_name=profile,
        format_name=format_name,
    )
    if not target.exists():
        raise FileApiError(
            "export_output_missing",
            "The engine reported success but did not create an export file.",
            status=500,
        )
    viewer = getattr(app, "viewer", None)
    if viewer is not None:
        viewer.report_export(report)
    output = target
    content_type = "application/octet-stream"
    output_name = filename
    if format_name == "gltf":
        output = _zip_gltf_outputs(target.parent, filename)
        output_name = output.name
        content_type = "application/zip"
    elif format_name == "glb":
        content_type = "model/gltf-binary"
    context.report(1.0, report.banner)
    return FileOperationResult(
        path=output,
        filename=output_name,
        content_type=content_type,
        format=format_name,
        message=report.banner,
    )


def build_file_operations(app: Any) -> dict[str, Callable[[FileJobContext], FileOperationResult]]:
    """Return callbacks that keep all file mutations on the live app graph."""
    return {
        "save-project": lambda context: _save(app, context),
        "save-as": lambda context: _save(app, context),
        "import-model": lambda context: _import(app, context),
        "open-project": lambda context: _open(app, context),
        "export-model": lambda context: _export(app, context),
    }
