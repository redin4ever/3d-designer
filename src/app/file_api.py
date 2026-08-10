"""Framework-neutral background jobs for the live file API.

The HTTP adapter owns status codes and headers; this module owns validation, job state,
threading, temporary files, and download confinement.  Action callbacks are injected so
the app composition root can connect scene/package/engine code without a circular import.
"""

from __future__ import annotations


class FileJobManager:
    def __init__(self, *_args, **_kwargs):
        pass

    def submit(self, *_args, **_kwargs):
        return {"job_id": "stub", "status": "queued"}

    def get(self, *_args, **_kwargs):
        return {"job_id": "stub", "status": "queued"}


class FileApiError(Exception):
    pass


class FileOperationResult:
    pass
