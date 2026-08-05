"""Stub — round-tripping the document to disk: ``save``, ``load`` (ADR-002, ADR-006).

The ``.blend`` file is a cache, not the record — this module is what makes that true. What
is saved is the operation log, the head, checkpoints and barriers; geometry is never
written here and is rebuilt by calling ``.replay()`` after ``load``.

**Chosen file format**, since nothing in ``src/contracts/`` fixes one: a single JSON
object, written by ``save`` and read by ``load``, shaped like::

    {
      "schema_version": 1,           # contracts.SCHEMA_VERSION at save time
      "scene_id": "...",
      "unit_scale": 1.0,
      "phase": "blockout",
      "check_cadence": "every_geometry_change",
      "engine_backend": "fake",
      "metadata": {},
      "head": 3,
      "operations": [ {"op_id": "...", "kind": "...", "params": {...}, "phase": "...",
                        "author": "...", "target_objects": [...], "opaque": false,
                        "produced_objects": [...], "status": "applied"}, ... ],
      "checkpoints": [ {"name": "...", "index": 2, "phase": "blockout", "note": "..."} ],
      "barriers": [ {"index": 1, "op_id": "...", "reason": "...",
                      "snapshot_path": "..."} ]
    }

``active_lease`` is **not** persisted. A lease is proof that one specific run currently
holds the write lock (ADR-007); reloading a scene in a new process starts with no lock
held, the same as any other freshly constructed ``Scene``, rather than carrying forward a
lease no live holder can prove.

**Known gap, not a contract problem**: ``Operation.placements``/``joinery``/``acceptance``
are tuples of their own nested dataclasses (``ConstraintSet``, ``JoineryIntent``,
``AcceptanceQuery``); a full round-trip needs to serialise those recursively too. No test
in ``persistence_test.py`` exercises an operation carrying any of the three — an
implementer adding that support should extend the per-operation shape above, not invent a
second format.

Nothing here is implemented yet.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from contracts import (
    SCHEMA_VERSION,
    CheckCadence,
    Checkpoint,
    EngineProtocol,
    HandlerRegistry,
    Operation,
    OperationStatus,
    Phase,
    UndoBarrier,
)

if TYPE_CHECKING:
    from . import Scene

__all__ = ["PersistenceMixin"]

_NOT_IMPLEMENTED = "scene.{name}: not implemented"


def _operation_to_dict(op: Operation) -> dict[str, Any]:
    return {
        "op_id": op.op_id,
        "kind": op.kind,
        "params": op.params,
        "phase": op.phase,
        "author": op.author,
        "target_objects": list(op.target_objects),
        "opaque": op.opaque,
        "produced_objects": list(op.produced_objects),
        "status": str(op.status),
    }


def _operation_from_dict(data: dict[str, Any]) -> Operation:
    return Operation(
        op_id=data["op_id"],
        kind=data["kind"],
        params=data.get("params", {}),
        phase=data.get("phase", "blockout"),
        author=data.get("author", ""),
        target_objects=tuple(data.get("target_objects", ())),
        opaque=data.get("opaque", False),
        produced_objects=tuple(data.get("produced_objects", ())),
        status=OperationStatus(data.get("status", "pending")),
    )


class PersistenceMixin:
    """``save``/``load``. See the module docstring for the chosen file format."""

    def save(self, path: str) -> None:
        """Write the document (log, head, checkpoints, barriers, metadata) to ``path`` as
        JSON, per the shape documented above. Never writes geometry — that is what
        ``replay()`` is for after a ``load``.
        """
        doc = self._document
        data = {
            "schema_version": doc.schema_version,
            "scene_id": doc.scene_id,
            "unit_scale": doc.unit_scale,
            "phase": str(doc.phase),
            "check_cadence": str(doc.check_cadence),
            "engine_backend": doc.engine_backend,
            "metadata": doc.metadata,
            "head": doc.head,
            "operations": [_operation_to_dict(op) for op in doc.operations],
            "checkpoints": [
                {
                    "name": c.name,
                    "index": c.index,
                    "phase": str(c.phase),
                    "note": c.note,
                }
                for c in doc.checkpoints
            ],
            "barriers": [
                {
                    "index": b.index,
                    "op_id": b.op_id,
                    "reason": b.reason,
                    "snapshot_path": b.snapshot_path,
                }
                for b in doc.barriers
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load(path: str, engine: EngineProtocol, handlers: HandlerRegistry) -> "Scene":
        """Read ``path``, construct a new ``Scene`` around ``engine``/``handlers``, and
        restore its document — but **not** its geometry; the caller must call
        ``.replay()`` on the result to rebuild it.

        Once implemented, must check ``data["schema_version"] > contracts.SCHEMA_VERSION``
        **before** attempting to interpret the rest of the file, and raise ``ValueError``
        with a message containing the substring ``"schema_version"`` when it is newer
        than this code understands. A file from a future version may use operation kinds,
        params shapes or barrier semantics this code has never seen; silently loading it
        as best-effort is how a scene gets quietly misread rather than loudly rejected.
        See ``persistence_test.py::test_load_of_a_newer_schema_version_fails_loudly``.
        """
        from . import Scene  # deferred: avoids a circular import with scene/__init__.py

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data["schema_version"] > SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {data['schema_version']} is newer than this code "
                f"understands (supports up to {SCHEMA_VERSION}). Refusing to guess at "
                "operation kinds, params shapes or barrier semantics it has never seen."
            )

        scene = Scene(engine, handlers, scene_id=data.get("scene_id", ""))
        doc = scene.document
        doc.schema_version = data["schema_version"]
        doc.unit_scale = data.get("unit_scale", 1.0)
        doc.phase = Phase(data.get("phase", "blockout"))
        doc.check_cadence = CheckCadence(
            data.get("check_cadence", "every_geometry_change")
        )
        doc.engine_backend = data.get("engine_backend", engine.backend_name)
        doc.metadata = data.get("metadata", {})
        doc.operations = [_operation_from_dict(o) for o in data.get("operations", [])]
        doc.head = data["head"]
        doc.checkpoints = [
            Checkpoint(
                name=c["name"], index=c["index"], phase=Phase(c["phase"]), note=c.get("note", "")
            )
            for c in data.get("checkpoints", [])
        ]
        doc.barriers = [
            UndoBarrier(
                index=b["index"],
                op_id=b["op_id"],
                reason=b["reason"],
                snapshot_path=b["snapshot_path"],
            )
            for b in data.get("barriers", [])
        ]
        return scene
