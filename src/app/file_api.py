"""Framework-neutral background jobs for the live file API.

The HTTP adapter owns status codes and headers; this module owns validation, job state,
threading, temporary files, and download confinement. Action callbacks are injected so
the app composition root can connect scene/package/engine code without a circular import.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

MAX_UPLOAD_BYTES = 512 * 1024 * 1024
FILE_ACTIONS = frozenset({"open-project", "save-project", "save-as", "import-model", "export-model"})
_BINARY_ACTIONS = frozenset({"open-project", "import-model"})
_FORMAT_TYPES = {
    "glb": "model/gltf-binary",
    "gltf": "model/gltf+json",
    "obj": "model/obj",
    "fbx": "application/octet-stream",
    "stl": "model/stl",
    "ply": "application/ply",
    "usd": "model/vnd.usd+zip",
    "usda": "model/vnd.usda",
    "usdc": "model/vnd.usdc",
    "forge3d": "application/vnd.forge3d+zip",
}


class FileApiError(Exception):
    """A safe, structured error the HTTP adapter can serialize directly."""

    def __init__(self, code: str, message: str, *, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        error: dict[str, Any] = {"code": code, "message": message}
        if details is not None:
            error["details"] = details
        self.payload = {"ok": False, "error": error}


@dataclass(frozen=True)
class FileOperationResult:
    """Optional output returned by an injected action callback."""

    data: bytes | bytearray | None = None
    path: Path | None = None
    filename: str | None = None
    content_type: str | None = None
    format: str | None = None
    message: str = "Complete."


@dataclass
class FileJobContext:
    """The only contract an action callback needs to know about."""

    job_id: str
    action: str
    payload: dict[str, Any]
    source_path: Path
    output_dir: Path
    filename: str
    cancel_event: threading.Event
    _report: Callable[[float, str], None]

    def report(self, progress: float, message: str = "") -> None:
        self._report(progress, message)


@dataclass
class _Job:
    job_id: str
    action: str
    payload: dict[str, Any]
    filename: str
    source_root: Path
    source_path: Path
    output_dir: Path
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued."
    error: dict[str, Any] | None = None
    download_token: str | None = None
    download_filename: str | None = None
    download_type: str | None = None
    future: Future | None = None


def _safe_filename(value: Any, fallback: str) -> str:
    """Return a deterministic basename that cannot escape a managed directory."""
    raw = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    raw = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    raw = raw.lstrip(".")
    return raw or fallback


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


class FileJobManager:
    """Thread-safe job manager used by the live server's file endpoints.

    ``operations`` maps an action name to a callable accepting :class:`FileJobContext`.
    Callbacks may return ``FileOperationResult``, bytes, a path, a mapping with those keys,
    or ``None``. They can report progress and should observe ``cancel_event`` for expensive
    work. The manager never imports scene, engine, or HTTP modules.
    """

    def __init__(
        self,
        work_root: str | Path,
        *,
        operations: Mapping[str, Callable[[FileJobContext], Any]] | None = None,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
        max_workers: int = 2,
    ):
        self.work_root = Path(work_root).resolve()
        self.upload_root = self.work_root / "uploads"
        self.download_root = self.work_root / "downloads"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.download_root.mkdir(parents=True, exist_ok=True)
        self.operations = dict(operations or {})
        self.max_upload_bytes = int(max_upload_bytes)
        if self.max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._downloads: dict[str, tuple[Path, str, str]] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="forge3d-file")
        self._closed = False

    def submit(self, headers: Mapping[str, str] | None, body: bytes | bytearray | memoryview) -> dict[str, Any]:
        """Validate a browser request, persist its local bytes, and queue a job.

        JSON requests contain ``action`` in their object. Binary requests carry the action
        and filename in the ``x-forge3d-*`` headers used by ``frontend/src/file-io.js``.
        No path, URL, or remote fetch is accepted as a substitute for uploaded bytes.
        """
        if self._closed:
            raise FileApiError("service_closed", "The file service is closed.", status=503)
        normalized = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
        raw = bytes(body or b"")
        declared = normalized.get("x-forge3d-size")
        if declared is not None:
            try:
                if int(declared) != len(raw):
                    raise FileApiError("size_mismatch", "The announced file size does not match the upload.")
            except ValueError as exc:
                raise FileApiError("invalid_size", "The announced file size is invalid.") from exc
        if len(raw) > self.max_upload_bytes:
            limit = (
                f"{self.max_upload_bytes / (1024 * 1024):g} MiB"
                if self.max_upload_bytes >= 1024 * 1024
                else f"{self.max_upload_bytes} bytes"
            )
            raise FileApiError("upload_too_large", f"Files must be {limit} or smaller.", status=413)
        content_type = normalized.get("content-type", "").split(";", 1)[0].strip().lower()
        is_json = content_type == "application/json"
        payload: dict[str, Any]
        if is_json:
            try:
                decoded = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FileApiError("invalid_json", "The file request body is not valid JSON.") from exc
            if not isinstance(decoded, dict):
                raise FileApiError("invalid_json", "The file request body must be a JSON object.")
            payload = dict(decoded)
            action = str(payload.get("action", "")).strip().lower()
        else:
            action = normalized.get("x-forge3d-action", "").strip().lower()
            payload = {}

        if action == "import-model" and not is_json:
            source_up = normalized.get("x-forge3d-source-up", "AUTO").upper()
            if source_up not in {"AUTO", "X", "Y", "Z"}:
                raise FileApiError("invalid_source_up", "Source up must be AUTO, X, Y, or Z.")
            try:
                unit_scale = float(normalized.get("x-forge3d-unit-scale", "1"))
            except ValueError as exc:
                raise FileApiError("invalid_unit_scale", "Unit scale must be a positive number.") from exc
            if unit_scale <= 0:
                raise FileApiError("invalid_unit_scale", "Unit scale must be a positive number.")
            flatten_raw = normalized.get("x-forge3d-flatten", "true").lower()
            if flatten_raw not in {"true", "false"}:
                raise FileApiError("invalid_flatten", "Flatten must be true or false.")
            payload = {
                "source_up": source_up,
                "unit_scale": unit_scale,
                "flatten": flatten_raw == "true",
            }

        if action not in FILE_ACTIONS:
            raise FileApiError("unsupported_action", f"Unsupported file action {action!r}.")
        if action in _BINARY_ACTIONS and is_json:
            if payload.get("path") or payload.get("url"):
                raise FileApiError(
                    "local_file_required",
                    "Upload a local binary file; paths and URLs are not accepted.",
                )
            raise FileApiError("local_file_required", "Upload the local binary file in the request body.")
        if action not in _BINARY_ACTIONS and not is_json:
            raise FileApiError("json_required", f"{action} requests must use application/json.")

        extension = str(payload.get("format", "")).lower().lstrip(".")
        default_name = (
            normalized.get("x-forge3d-filename")
            if action in _BINARY_ACTIONS
            else payload.get("filename")
        ) or (f"scene.{extension}" if extension else ("scene.forge3d" if action in {"save-project", "save-as"} else "scene.glb"))
        filename = _safe_filename(default_name, "scene.bin")
        job_id = uuid.uuid4().hex
        source_root = self.upload_root / "jobs" / job_id
        source_root.mkdir(parents=True, exist_ok=True)
        source_path = source_root / filename
        if action in _BINARY_ACTIONS:
            digest = hashlib.sha256(raw).hexdigest()
            content_root = self.upload_root / "content" / digest
            content_root.mkdir(parents=True, exist_ok=True)
            content_path = content_root / filename
            if not content_path.exists():
                content_path.write_bytes(raw)
            shutil.copyfile(content_path, source_path)
        else:
            source_path = source_root

        output_dir = self.download_root / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        job = _Job(
            job_id=job_id,
            action=action,
            payload=payload,
            filename=filename,
            source_root=source_root,
            source_path=source_path,
            output_dir=output_dir,
        )
        with self._lock:
            self._jobs[job_id] = job
            try:
                job.future = self._executor.submit(self._run, job)
            except RuntimeError as exc:
                self._jobs.pop(job_id, None)
                self._remove_tree(source_root.parent if source_root.parent.name == "jobs" else source_root)
                self._remove_tree(output_dir)
                raise FileApiError("service_closed", "The file service is closed.", status=503) from exc
        return self._public(job)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                raise FileApiError("unknown_job", f"Unknown file job {job_id!r}.", status=404)
            return self._public(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                raise FileApiError("unknown_job", f"Unknown file job {job_id!r}.", status=404)
            if job.status in {"complete", "failed", "cancelled"}:
                return self._public(job)
            job.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.message = "Cancelled."
            else:
                job.status = "cancelling"
                job.message = "Cancelling."
            return self._public(job)

    def register_download(self, path: str | Path, filename: str, content_type: str) -> str:
        """Register an existing managed file and return an opaque download token."""
        resolved = self._confined(Path(path), self.download_root)
        if not resolved.is_file():
            raise FileApiError("download_missing", "The generated download does not exist.", status=404)
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._downloads[token] = (resolved, _safe_filename(filename, "download.bin"), content_type)
        return token

    def download_path(self, token: str) -> Path:
        with self._lock:
            entry = self._downloads.get(str(token))
            if entry is None:
                raise FileApiError("unknown_download", "Unknown or expired download token.", status=404)
            path = self._confined(entry[0], self.download_root)
            if not path.is_file():
                raise FileApiError("download_missing", "The generated download no longer exists.", status=404)
            return path

    def read_download(self, token: str) -> tuple[bytes, str, str]:
        with self._lock:
            entry = self._downloads.get(str(token))
            if entry is None:
                raise FileApiError("unknown_download", "Unknown or expired download token.", status=404)
            path = self._confined(entry[0], self.download_root)
            if not path.is_file():
                raise FileApiError("download_missing", "The generated download no longer exists.", status=404)
            try:
                return path.read_bytes(), entry[1], entry[2]
            except OSError as exc:
                raise FileApiError("download_unreadable", "The generated download cannot be read.", status=500) from exc

    def cleanup(self, job_id: str | None = None) -> None:
        """Remove terminal job files and invalidate their download tokens."""
        with self._lock:
            ids = [str(job_id)] if job_id is not None else list(self._jobs)
            for current_id in ids:
                job = self._jobs.get(current_id)
                if job is None:
                    continue
                if job.status not in {"complete", "failed", "cancelled"}:
                    continue
                tokens = [token for token, entry in self._downloads.items() if entry[0].is_relative_to(job.output_dir.resolve())]
                for token in tokens:
                    self._downloads.pop(token, None)
                self._remove_tree(job.source_root)
                self._remove_tree(job.output_dir)
                self._jobs.pop(current_id, None)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)
        self.cleanup()

    def _run(self, job: _Job) -> None:
        with self._lock:
            if job.cancel_event.is_set() or job.status == "cancelled":
                job.status = "cancelled"
                job.message = "Cancelled."
                return
            job.status = "running"
            job.message = "Running."
        callback = self.operations.get(job.action) or self.operations.get("save-project" if job.action == "save-as" else job.action)
        if callback is None:
            self._fail(job, "operation_unavailable", f"No operation is configured for {job.action!r}.")
            return
        context = FileJobContext(
            job_id=job.job_id,
            action=job.action,
            payload=dict(job.payload),
            source_path=job.source_path,
            output_dir=job.output_dir,
            filename=job.filename,
            cancel_event=job.cancel_event,
            _report=lambda progress, message="": self._report(job, progress, message),
        )
        try:
            result = callback(context)
            with self._lock:
                if job.cancel_event.is_set() or job.status == "cancelling":
                    job.status = "cancelled"
                    job.message = "Cancelled."
                    return
            normalized = self._normalize_result(result, job)
            if normalized.data is not None or normalized.path is not None:
                path = self._materialize(normalized, job)
                token = self.register_download(path, normalized.filename or job.filename, normalized.content_type or _FORMAT_TYPES.get(_extension(normalized.filename or job.filename), "application/octet-stream"))
                with self._lock:
                    job.download_token = token
                    job.download_filename = _safe_filename(normalized.filename or job.filename, "download.bin")
                    job.download_type = normalized.content_type or "application/octet-stream"
            with self._lock:
                job.status = "complete"
                job.progress = 1.0
                job.message = normalized.message or "Complete."
        except FileApiError as exc:
            self._fail(job, exc.code, exc.message, details=exc.payload["error"].get("details"))
        except Exception as exc:  # noqa: BLE001 - callback failures become API data
            self._fail(job, "operation_failed", str(exc) or exc.__class__.__name__)

    def _normalize_result(self, result: Any, job: _Job) -> FileOperationResult:
        if result is None:
            return FileOperationResult(message="Complete.")
        if isinstance(result, FileOperationResult):
            return result
        if isinstance(result, (bytes, bytearray)):
            return FileOperationResult(data=bytes(result), filename=job.filename)
        if isinstance(result, (str, Path)):
            return FileOperationResult(path=Path(result), filename=job.filename)
        if isinstance(result, Mapping):
            data = result.get("data")
            return FileOperationResult(
                data=bytes(data) if isinstance(data, (bytes, bytearray)) else None,
                path=Path(result["path"]) if result.get("path") is not None else None,
                filename=result.get("filename") or job.filename,
                content_type=result.get("content_type"),
                format=result.get("format"),
                message=str(result.get("message") or "Complete."),
            )
        raise FileApiError("invalid_operation_result", "The file operation returned an unsupported result.")

    def _materialize(self, result: FileOperationResult, job: _Job) -> Path:
        filename = _safe_filename(result.filename or job.filename, "download.bin")
        target = self._confined(job.output_dir / filename, self.download_root)
        if result.data is not None:
            target.write_bytes(bytes(result.data))
            return target
        if result.path is None:
            raise FileApiError("invalid_operation_result", "The file operation did not provide output data.")
        source = Path(result.path).resolve()
        if not source.is_file():
            raise FileApiError("download_missing", "The file operation output does not exist.")
        shutil.copyfile(source, target)
        return target

    def _report(self, job: _Job, progress: float, message: str) -> None:
        with self._lock:
            if job.status in {"complete", "failed", "cancelled"}:
                return
            job.progress = max(0.0, min(1.0, float(progress)))
            job.message = str(message)

    def _fail(self, job: _Job, code: str, message: str, *, details: Any = None) -> None:
        with self._lock:
            job.status = "failed"
            job.progress = max(0.0, min(1.0, job.progress))
            error: dict[str, Any] = {"code": code, "message": message}
            if details is not None:
                error["details"] = details
            job.error = error
            job.message = message

    def _public(self, job: _Job) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {
                "ok": job.status not in {"failed"},
                "job_id": job.job_id,
                "status": job.status,
                "action": job.action,
                "progress": job.progress,
                "message": job.message,
                "filename": job.download_filename or job.filename,
            }
            if job.error is not None:
                result["ok"] = False
                result["error"] = dict(job.error)
            if job.download_token is not None:
                result["download_token"] = job.download_token
                result["download_url"] = f"/api/file-io/downloads/{job.download_token}"
                result["content_type"] = job.download_type
            return result

    def _confined(self, path: Path, root: Path) -> Path:
        resolved_root = root.resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(resolved_root):
            raise FileApiError("download_path_forbidden", "The requested path is outside the managed download directory.", status=400)
        return resolved

    @staticmethod
    def _remove_tree(path: Path) -> None:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            return


__all__ = [
    "FILE_ACTIONS",
    "MAX_UPLOAD_BYTES",
    "FileApiError",
    "FileJobContext",
    "FileJobManager",
    "FileOperationResult",
]
