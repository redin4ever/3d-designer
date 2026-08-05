"""Stub — turning the operation log into geometry: ``apply`` and ``replay`` (ADR-002).

The log is the source of truth. ``apply`` is the only way an operation joins it;
``replay`` is the only way geometry is rebuilt from it. Every other file in this package
calls one or both of these rather than touching ``SceneDocument`` or the engine directly.

Nothing here is implemented yet. Every body raises until an implementer replaces it; the
signatures and the contract described below do not move.
"""

from __future__ import annotations

from contracts import (
    ChangeKind,
    LockContention,
    Operation,
    OperationResult,
    SceneChangeEvent,
    WriteLease,
)

__all__ = ["DocumentMixin"]

_NOT_IMPLEMENTED = "scene.{name}: not implemented"


class DocumentMixin:
    """``apply``/``replay``. Mixed into :class:`scene.Scene`; ``self`` is expected to carry
    ``_engine``, ``_handlers``, ``_document`` and ``_cache`` (this file and ``cache.py``)
    plus ``_emit`` (``events.py``) — see ``scene/__init__.py``."""

    def apply(
        self, op: Operation, *, lease: WriteLease | None = None, snapshot_path: str = ""
    ) -> OperationResult:
        """Run ``op`` against the live engine and, only on success, record it in the log.

        Once implemented, this method must, in this order:

        1. **Resolve the handler**: ``self._handlers[op.kind]``. An unregistered kind
           raises ``KeyError`` naming the kinds that *are* registered (the same
           helpfulness ``SceneDocument.checkpoint`` gives for an unknown checkpoint
           name) — before anything else runs, so a typo'd ``kind`` never reaches the
           engine.
        2. **Check the write lock.** ADR-007's single-writer guarantee, enforced here
           because ``orchestration`` (which will eventually own acquiring leases) does
           not exist yet and ``scene`` must be usable stand-alone until it does. Chosen
           rule (see ``README.md``'s "Write lock" section for the reasoning):

           - ``self._document.active_lease is None`` (nobody has ever acquired the
             lock — genuine single-agent use) → proceed regardless of ``lease``. This is
             a deliberate single-agent allowance, not a general bypass.
           - ``active_lease is not None`` and ``lease is None`` → raise
             ``contracts.LockContention`` naming the current holder.
           - ``active_lease is not None`` and ``lease`` is given → delegate to
             ``self._document.require_lease(lease)``, which raises ``LockContention`` on
             any mismatch.
        3. **Pre-validate what ``SceneDocument.append`` will validate** — a duplicate
           ``op.op_id`` and an ``op.opaque`` operation with no ``snapshot_path`` — before
           calling the handler. Doing this after the handler runs would mean a rejected
           append leaves engine-side effects that were never logged, which is worse than
           the failure this ordering prevents.
        4. **Call the handler**: ``self._handlers[op.kind](self._engine, op)``. Let any
           exception it raises propagate to the caller completely unchanged — do not
           catch it, do not append, do not emit. The log, the cache and the engine must
           be exactly as observable as they were before this call. This is the
           "failure" contract: a failed operation is never half-recorded.
        5. **On ``OperationResult.ok is False``**: return the result as-is. Do not
           append, do not emit. A reported failure and a raised exception both mean
           "nothing changed" as far as the log is concerned.
        6. **On success**: ``self._document.append(op, snapshot_path=snapshot_path)`` —
           through the document's own method, never by touching
           ``self._document.operations`` directly, so its truncate-on-append-after-undo
           behaviour actually runs. Then call ``self.invalidate_cache`` for every id in
           ``result.produced_objects + result.modified_objects + result.removed_objects``,
           emit exactly one ``contracts.SceneChangeEvent`` via ``self._emit`` carrying
           ``op.op_id`` and those ids in ``highlight``, and return ``result``.

        Whether the stored log entry is ``op`` itself or a copy with
        ``status=OperationStatus.APPLIED`` (via ``dataclasses.replace``, since
        ``Operation`` is frozen) is left to the implementer — no test in this package
        depends on ``Operation.status`` either way.

        ``lease=None`` is a valid, intentional default — see point 2. It is not an
        oversight that the signature allows it.
        """
        if op.kind not in self._handlers:
            known = ", ".join(sorted(self._handlers)) or "(none)"
            raise KeyError(
                f"unknown operation kind {op.kind!r}; known kinds: {known}"
            )

        active_lease = self._document.active_lease
        if active_lease is not None:
            if lease is None:
                raise LockContention(
                    holder=active_lease.holder, expires_at_op=active_lease.expires_at_op
                )
            self._document.require_lease(lease)

        # Pre-validate what SceneDocument.append will validate, before the handler runs
        # (see point 3 above) — a rejected append must never leave engine-side effects
        # that were never logged.
        if any(existing.op_id == op.op_id for existing in self._document.operations):
            raise ValueError(
                f"operation id {op.op_id!r} is already in the log. Ids key the geometry "
                "cache, so a duplicate silently overwrites an earlier result."
            )
        if op.opaque and not snapshot_path:
            raise ValueError(
                f"operation {op.op_id!r} is opaque but no snapshot path was given. An "
                "opaque operation cannot be replayed, so rolling back across it needs a "
                "snapshot — capture one before appending."
            )

        result = self._handlers[op.kind](self._engine, op)

        if not result.ok:
            return result

        self._document.append(op, snapshot_path=snapshot_path)

        touched = (*result.produced_objects, *result.modified_objects, *result.removed_objects)
        for object_id in touched:
            self.invalidate_cache(object_id)

        if result.produced_objects:
            kind = ChangeKind.OBJECTS_ADDED
        elif result.removed_objects:
            kind = ChangeKind.OBJECTS_REMOVED
        else:
            kind = ChangeKind.OBJECTS_MODIFIED

        self._emit(
            SceneChangeEvent(
                kind=kind,
                op_id=op.op_id,
                object_ids=touched,
                highlight=touched,
                head=self._document.head,
            )
        )
        return result

    def replay(self) -> None:
        """Rebuild every object in the scene from the operation log, from nothing.

        Once implemented: ``self._engine.reset()``, clear the whole cache
        (``self._cache.clear()``), then call ``self._handlers[op.kind](self._engine,
        op)`` for every ``op`` in ``self._document.active_operations``, in order. Do not
        catch what a handler raises during replay — ``contracts.OperationHandler``'s own
        docstring requires a handler be deterministic (ADR-002), so a handler that raises
        on a second run against the same params is a determinism violation, and hiding it
        here would let a broken handler pass every test that only exercises ``apply``.

        Does **not** emit a ``SceneChangeEvent`` — ``replay`` is the low-level rebuild
        primitive; ``history.py``'s ``undo``/``redo``/``rollback_to`` are what call it and
        emit the one event that describes the result (``ChangeKind.ROLLBACK`` or
        ``ChangeKind.FULL_RESYNC``) to listeners.

        This is the property the whole undo model depends on: the same log, replayed,
        must produce byte-identical geometry every time. See
        ``document_test.py::test_replay_reproduces_identical_geometry`` — if this is not
        true, undo is not a pointer move and nothing else in this module is true.
        """
        self._engine.reset()
        self._cache.clear()
        for op in self._document.active_operations:
            self._handlers[op.kind](self._engine, op)
