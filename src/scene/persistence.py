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

from typing import TYPE_CHECKING

from contracts import EngineProtocol, HandlerRegistry

if TYPE_CHECKING:
    from . import Scene

__all__ = ["PersistenceMixin"]

_NOT_IMPLEMENTED = "scene.{name}: not implemented"


class PersistenceMixin:
    """``save``/``load``. See the module docstring for the chosen file format."""

    def save(self, path: str) -> None:
        """Write the document (log, head, checkpoints, barriers, metadata) to ``path`` as
        JSON, per the shape documented above. Never writes geometry — that is what
        ``replay()`` is for after a ``load``.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="save"))

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
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="load"))
