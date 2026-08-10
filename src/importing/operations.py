"""The opaque model-file import operation.

Blender owns interchange parsing and material/mesh creation. This module owns the
operation-log boundary: validate the local source before handing it to the engine, carry
every created id into the result, and turn non-fatal engine warnings into visible
assumptions. The operation is intentionally opaque because an interchange parser is not a
deterministic parametric operation that the scene log can replay.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from contracts import (
    EngineProtocol,
    ModelImportResult,
    Operation,
    OperationResult,
    RuleError,
    SUPPORTED_MODEL_EXTENSIONS,
    ToolError,
)

__all__ = [
    "IMPORT_OPERATION_KIND",
    "import_model_file",
    "make_import_operation",
]

IMPORT_OPERATION_KIND = "import_model_file"
_SOURCE_UP = ("AUTO", "X", "Y", "Z")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def _failure(rule: str, detail: str, suggestion: str) -> ToolError:
    """Create the one named failure shape exposed by operation boundaries."""
    return ToolError(rule=rule, detail=detail, suggestion=suggestion)


def _local_file(raw_path: object) -> tuple[str, Path]:
    """Validate and return a local source path without accepting URI schemes."""
    if not isinstance(raw_path, str) or not raw_path:
        raise _failure(
            "import.invalid_path",
            "path must be a non-empty local filesystem path",
            "pass the local path to a supported model file",
        )

    parsed = urlsplit(raw_path)
    # ``urlsplit`` interprets ``C:\\model.glb`` as scheme ``c``. Windows drive paths
    # are explicitly allowed; all other schemes, including ``file://``, are rejected so
    # this operation never turns into an implicit network fetch.
    if parsed.scheme and not _WINDOWS_DRIVE.match(raw_path):
        raise _failure(
            "import.local_path_required",
            f"{raw_path!r} is a URI, not a local filesystem path",
            "download the model first and pass its local path",
        )

    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise _failure(
            "import.file_not_found",
            f"no local model file exists at {raw_path!r}",
            "check the path and choose an existing local file",
        )

    extension = path.suffix.lower()
    if extension not in SUPPORTED_MODEL_EXTENSIONS:
        supported = ", ".join(SUPPORTED_MODEL_EXTENSIONS)
        raise _failure(
            "import.unsupported_format",
            f"model format {extension or '(none)'!r} is not supported",
            f"use one of: {supported}",
        )
    return str(path), path


def _params(op: Operation) -> tuple[str, str, float, bool]:
    """Validate operation parameters before Blender can create any objects."""
    params = op.params
    path, _ = _local_file(params.get("path"))

    source_up = params.get("source_up", "AUTO")
    if not isinstance(source_up, str) or source_up not in _SOURCE_UP:
        raise _failure(
            "import.invalid_source_up",
            f"source_up must be one of {_SOURCE_UP}, got {source_up!r}",
            f"choose one of: {', '.join(_SOURCE_UP)}",
        )

    unit_scale = params.get("unit_scale", 1.0)
    if isinstance(unit_scale, bool) or not isinstance(unit_scale, (int, float)) or unit_scale <= 0:
        raise _failure(
            "import.invalid_unit_scale",
            f"unit_scale must be a positive number, got {unit_scale!r}",
            "pass a unit_scale greater than 0, such as 1.0 or 0.01",
        )

    flatten = params.get("flatten", True)
    if not isinstance(flatten, bool):
        raise _failure(
            "import.invalid_flatten",
            f"flatten must be a boolean, got {flatten!r}",
            "pass true to flatten meshes or false to preserve imported hierarchy",
        )
    return path, source_up, float(unit_scale), flatten


def import_model_file(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Import one local model and report all created objects and ignored content.

    The scene applies this handler once; because the corresponding operation is opaque,
    later undo/redo crosses its geometry snapshot barrier instead of replaying Blender's
    importer. Engine rule failures retain their meaningful names, while unexpected adapter
    failures are wrapped so an agent never receives a raw traceback as the operation result.
    """
    path, source_up, unit_scale, flatten = _params(op)
    try:
        result = engine.import_model(
            path,
            source_up=source_up,
            unit_scale=unit_scale,
            flatten=flatten,
        )
    except RuleError:
        raise
    except FileNotFoundError as exc:
        raise _failure(
            "import.file_not_found",
            f"the engine could not open local model {path!r}: {exc}",
            "check that the local file still exists and is readable",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - adapter boundary must name every failure
        raise _failure(
            "import.engine_failed",
            f"the engine could not import {path!r}: {exc}",
            "verify the file is valid and supported by the connected Blender engine",
        ) from exc

    if not isinstance(result, ModelImportResult):
        raise _failure(
            "import.invalid_engine_result",
            f"the engine returned {type(result).__name__}, not ModelImportResult",
            "reconnect the Blender engine and retry the import",
        )
    return OperationResult(
        op_id=op.op_id,
        ok=True,
        produced_objects=result.object_ids,
        assumptions=result.warnings,
    )


def make_import_operation(
    op_id: str,
    path: str,
    *,
    source_up: str = "AUTO",
    unit_scale: float = 1.0,
    flatten: bool = True,
    phase: str = "blockout",
    author: str = "",
) -> Operation:
    """Construct the one opaque operation record used by main wiring and callers."""
    return Operation(
        op_id=op_id,
        kind=IMPORT_OPERATION_KIND,
        params={
            "path": path,
            "source_up": source_up,
            "unit_scale": unit_scale,
            "flatten": flatten,
        },
        phase=phase,
        author=author,
        opaque=True,
    )
