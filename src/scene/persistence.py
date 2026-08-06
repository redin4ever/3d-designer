"""Round-tripping the document to disk: ``save``, ``load`` (ADR-002, ADR-006, ADR-015).

The ``.blend`` file is a cache, not the record — this module is what makes that true. What
is saved is the operation log, the head, checkpoints and barriers; geometry is never
written here and is rebuilt by calling ``.replay()`` after ``load``.

**Chosen file format**, since nothing in ``src/contracts/`` fixes one: a single JSON
object, written by ``save`` and read by ``load``, shaped like::

    {
      "schema_version": 2,           # contracts.SCHEMA_VERSION at save time
      "scene_id": "...",
      "unit_scale": 1.0,
      "phase": "blockout",
      "check_cadence": "every_geometry_change",
      "engine_backend": "fake",
      "metadata": {},
      "head": 3,
      "operations": [ ... ],         # every field of Operation — see op_codec.py
      "checkpoints": [ {"name": "...", "index": 2, "phase": "blockout", "note": "..."} ],
      "barriers": [ {"index": 1, "op_id": "...", "reason": "...",
                      "snapshot_path": "..."} ],
      "geometry_states": {"1": "/path/before.json", "2": "/path/after.json"}
    }

``active_lease`` is **not** persisted. A lease is proof that one specific run currently
holds the write lock (ADR-007); reloading a scene in a new process starts with no lock
held, the same as any other freshly constructed ``Scene``, rather than carrying forward a
lease no live holder can prove.

``geometry_states`` maps a log position to the geometry snapshot that describes it (see
``barriers.py``). Paths, not contents — these are session-scoped temp files, and a reload
whose snapshots have been cleaned away degrades to a replay rather than failing.

**Schema version 2 (ADR-015, Gate B 1.2).** Version 1 serialised nine of ``Operation``'s
fields and silently dropped ``placements`` (the ``ConstraintSet``), ``joinery``,
``acceptance``, ``asset_class`` and ``proposal_id``. So a saved scene came back with its
geometry and without the reason for it: move the wall, and the railing constrained to its
outer edge did not follow — which is ADR-002's entire stated reason for choosing a
parametric document. The per-operation shape now lives in ``op_codec.py`` and carries all
of them, nested dataclasses included.

A version-1 file still loads, and **warns while doing so**, naming what was never in it.
Loading one silently would reproduce the original bug one layer up: a scene that looks
intact and has quietly lost the reason for its geometry. A version newer than
:data:`contracts.SCHEMA_VERSION`, or older than :data:`contracts.MIN_READABLE_SCHEMA`,
stays a refusal.
"""

from __future__ import annotations

import json
import warnings
from typing import TYPE_CHECKING, Any

from contracts import (
    MIN_READABLE_SCHEMA,
    SCHEMA_VERSION,
    CheckCadence,
    Checkpoint,
    EngineProtocol,
    HandlerRegistry,
    Phase,
    UndoBarrier,
)

from .barriers import SnapshotLedger
from .op_codec import V1_DROPPED_FIELDS, operation_from_dict, operation_to_dict

if TYPE_CHECKING:
    from . import Scene

__all__ = ["PersistenceMixin"]


def _check_version(version: Any) -> None:
    """Refuse anything this build cannot read, before interpreting a single field.

    Both directions are refusals rather than best-effort reads. A newer file may use
    operation kinds, params shapes or barrier semantics this code has never seen; an older
    one predates the fields this code assumes. Guessing at either is how a scene gets
    quietly misread instead of loudly rejected.
    """
    if not isinstance(version, int):
        raise ValueError(
            f"schema_version {version!r} is not a version number. This is either not a "
            "forge3d scene document or it has been edited by hand."
        )
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"schema_version {version} is newer than this code understands (supports up "
            f"to {SCHEMA_VERSION}). Refusing to guess at operation kinds, params shapes "
            "or barrier semantics it has never seen."
        )
    if version < MIN_READABLE_SCHEMA:
        raise ValueError(
            f"schema_version {version} is older than the oldest this build can open "
            f"(MIN_READABLE_SCHEMA is {MIN_READABLE_SCHEMA}). Open it with the build that "
            "wrote it and save it forward."
        )


def _warn_about_old_schema(version: int, path: str) -> None:
    """Say what an older file could not bring with it.

    Not a debug aid — the whole point of the version bump (ADR-015). A v1 file genuinely
    has no constraints stored, so a scene that reloads looking intact has silently lost
    the thing that makes it parametric, and the only moment anyone can be told is now.
    """
    if version >= SCHEMA_VERSION:
        return
    warnings.warn(
        f"{path}: schema_version {version} predates schema_version {SCHEMA_VERSION}, so "
        f"its operations never stored {', '.join(V1_DROPPED_FIELDS)}. The geometry will "
        "rebuild; the constraints behind it will not, so placement will not re-solve when "
        "an anchor moves. Re-saving this scene writes it as version "
        f"{SCHEMA_VERSION}, but it cannot recover what was never in the file.",
        UserWarning,
        stacklevel=3,
    )


class PersistenceMixin:
    """``save``/``load``. See the module docstring for the chosen file format."""

    def save(self, path: str) -> None:
        """Write the document (log, head, checkpoints, barriers, metadata) to ``path`` as
        JSON, per the shape documented above. Never writes geometry — that is what
        ``replay()`` is for after a ``load``.

        Always stamps :data:`contracts.SCHEMA_VERSION` rather than whatever version the
        document was read at: what is being written is this build's format, and a file
        labelled v1 that carries v2 fields is worse than either honest version.
        """
        doc = self._document
        data = {
            "schema_version": SCHEMA_VERSION,
            "scene_id": doc.scene_id,
            "unit_scale": doc.unit_scale,
            "phase": str(doc.phase),
            "check_cadence": str(doc.check_cadence),
            "engine_backend": doc.engine_backend,
            "metadata": doc.metadata,
            "head": doc.head,
            "operations": [operation_to_dict(op) for op in doc.operations],
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
            "geometry_states": self._snapshots.to_json(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load(path: str, engine: EngineProtocol, handlers: HandlerRegistry) -> "Scene":
        """Read ``path``, construct a new ``Scene`` around ``engine``/``handlers``, and
        restore its document — but **not** its geometry; the caller must call
        ``.replay()`` on the result to rebuild it.

        Version is checked before any other field is interpreted (see
        :func:`_check_version`), and an older-but-readable one warns before returning (see
        :func:`_warn_about_old_schema`).
        """
        from . import Scene  # deferred: avoids a circular import with scene/__init__.py

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data["schema_version"]
        _check_version(version)

        scene = Scene(engine, handlers, scene_id=data.get("scene_id", ""))
        doc = scene.document
        doc.schema_version = SCHEMA_VERSION
        doc.unit_scale = data.get("unit_scale", 1.0)
        doc.phase = Phase(data.get("phase", "blockout"))
        doc.check_cadence = CheckCadence(
            data.get("check_cadence", "every_geometry_change")
        )
        doc.engine_backend = data.get("engine_backend", engine.backend_name)
        doc.metadata = data.get("metadata", {})
        doc.operations = [operation_from_dict(o) for o in data.get("operations", [])]
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
        scene._snapshots = SnapshotLedger.from_json(data.get("geometry_states"))
        # The reloaded log is the only record of what this scene can rebuild, so the
        # target ledger is recomputed from it rather than from whatever the engine happens
        # to hold — which, on a fresh engine, is nothing.
        scene._targets.rebuild(doc.operations, doc.head)

        _warn_about_old_schema(version, path)
        return scene
