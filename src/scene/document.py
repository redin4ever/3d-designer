"""Turning the operation log into geometry: ``apply`` and ``replay`` (ADR-002).

The log is the source of truth. ``apply`` is the only way an operation joins it;
``replay`` is the only way geometry is rebuilt from it. Every other file in this package
calls one or both of these rather than touching ``SceneDocument`` or the engine directly.

Three collaborators keep this file at one responsibility (Rule 2): ``targets.py`` decides
whether an operation could ever be re-run, ``barriers.py`` remembers which geometry
snapshot describes which point in the log, and ``geometry_snapshot.py`` reads and writes
those snapshots. What is left here is the loop itself.
"""

from __future__ import annotations

from dataclasses import replace

from contracts import (
    ChangeKind,
    LockContention,
    Operation,
    OperationResult,
    OperationStatus,
    SceneChangeEvent,
    WriteLease,
)

from .geometry_snapshot import capture, is_geometry_snapshot, restore, snapshot_directory
from .replay_report import ReplayReport, SkippedOperation

__all__ = ["DocumentMixin"]


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
           append, do not emit. The log, the cache and the engine must be exactly as
           observable as they were before this call. This is the "failure" contract: a
           failed operation is never half-recorded.

           That last sentence was a promise the code did not keep. A handler that created
           geometry and then raised left it live in the engine, unlogged — 29 orphaned
           parts from one failed ``add_railing``. The exception still propagates unchanged;
           what changed is that objects the failed attempt created are removed first
           (``_discard_orphans``), so the engine really is as it was found.
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

        **Added by F-010 (Gate B 5.2), between points 3 and 4:** an operation naming a
        target that no logged operation produced, and that was not in the engine when this
        scene was constructed, is refused here with ``scene.unknown_target`` before it can
        join the log. Such an operation cannot be re-run — geometry is rebuilt from
        ``engine.reset()`` — so recording it made every later ``undo``/``redo``/
        ``rollback_to`` in the session raise, three operations after the actual mistake.
        See ``targets.py``.
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
        self._targets.check(op)

        # The pre-execution state, taken here because this is the last moment it exists.
        # The caller's path is trusted only if it really is a geometry snapshot: the
        # shipped caller passed the result of `scene.save()`, which serialises the
        # operation log — and an opaque operation is by definition one the log does not
        # describe, so restoring from it restored nothing at all (F-011).
        before_state = ""
        if op.opaque:
            before_state = (
                snapshot_path
                if is_geometry_snapshot(snapshot_path)
                else self._write_geometry_snapshot(f"{op.op_id}.before")
            )

        # An operation is all-or-nothing. A handler that creates geometry and then fails
        # used to leave it live in the engine with no log entry: `add_railing` failing on
        # its third `create_mesh` left 29 orphaned parts behind. They then showed up in the
        # live view as geometry with no history, were counted by every measurement, and
        # vanished on the next save/load — because the log, which is the source of truth,
        # never knew about them. Snapshotting the object list is the cheapest way to make
        # the failure path leave the scene exactly as it found it.
        before = set(self._engine.list_objects())
        try:
            result = self._handlers[op.kind](self._engine, op)
        except Exception:
            self._discard_orphans(before)
            raise

        if not result.ok:
            self._discard_orphans(before)
            return result

        # What the operation made is recorded *on the log entry*, not only in the result:
        # the result is gone after this call, and the log has to be able to answer "could
        # this scene rebuild that object" on its own, including after a save and reload.
        produced = tuple(dict.fromkeys((*op.produced_objects, *result.produced_objects)))
        entry = replace(op, produced_objects=produced, status=OperationStatus.APPLIED)

        # Appending after an undo truncates the undone tail, at which point a stored index
        # would point into a log that no longer exists.
        if self._document.head < len(self._document.operations):
            self._snapshots.prune_beyond(self._document.head)

        self._document.append(entry, snapshot_path=snapshot_path)
        self._targets.record(produced)

        if op.opaque:
            # Both sides of the barrier. A pre-execution capture alone is enough to undo
            # back across it and not enough to redo forward over it — which is how one
            # redo of one raw script produced three differently-named objects (F-011).
            index = self._document.head - 1
            self._snapshots.register(
                index, before_state, self._write_geometry_snapshot(f"{op.op_id}.after")
            )

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

    def replay(self) -> ReplayReport:
        """Rebuild every object in the scene from the log, and say what that cost.

        Two things changed here after the product was run against real Blender, and both
        were session-fatal:

        **It no longer aborts.** It used to call every handler and let anything they raised
        propagate, on the reasoning that a handler which fails on a second run is violating
        the determinism ``contracts.OperationHandler`` requires. True, and beside the point:
        the log can also contain an operation that acts on geometry the log never made
        (``build_app(reset_scene=False)`` — open an existing ``.blend``), and *that*
        operation cannot re-run however deterministic its handler is. One of them in the
        log and every ``undo``/``redo``/``rollback_to`` for the rest of the session raised
        ``EngineError`` and never recovered. It now skips what it cannot run, records which
        one and why, and finishes the rest (F-010, Gate B 5.2).

        **It no longer starts from nothing when it does not have to.** Rebuilding from
        ``engine.reset()`` re-executes every logged operation, including opaque ones —
        arbitrary code that is not replayable by definition. A non-deterministic script
        therefore produced *different geometry* on every undo while the system reported a
        clean ``FULL_RESYNC`` (F-011, Gate B 5.3). It now restores the nearest geometry
        snapshot at or before the head and replays only what follows it, so an opaque
        operation is restored rather than re-run.

        Does **not** emit a ``SceneChangeEvent`` — ``replay`` is the low-level rebuild
        primitive; ``history.py``'s ``undo``/``redo``/``rollback_to`` are what call it and
        emit the one event that describes the result (``ChangeKind.ROLLBACK`` or
        ``ChangeKind.FULL_RESYNC``), carrying this report's summary in ``log_line``.

        The property the whole undo model depends on is unchanged: the same log, rebuilt,
        produces identical geometry every time. See
        ``document_test.py::test_replay_reproduces_identical_geometry``.
        """
        return self._rebuild_to(self._document.head)

    def _rebuild_to(self, head: int) -> ReplayReport:
        """Put the engine into the state the log describes at position ``head``."""
        self._cache.clear()
        base, restored_from = self._restore_nearest_state(head)
        applied, skipped = self._run_operations(self._document.operations[base:head])
        self._targets.rebuild(self._document.operations, head)
        report = ReplayReport(applied=applied, skipped=skipped, restored_from=restored_from)
        self._last_replay = report
        return report

    def _restore_nearest_state(self, head: int) -> tuple[int, str]:
        """Get as close to ``head`` as a captured snapshot allows; return where we landed.

        Nearest usable first, then progressively earlier ones: a snapshot file can be gone
        — these live in the system temp directory and sessions end — and an earlier base
        still beats ``reset()``, which would re-run every opaque operation between them.
        ``(0, "")`` means nothing was restorable and the engine was cleared.
        """
        for index, path in self._snapshots.candidates_for(head):
            if restore(self._engine, path):
                return index, path
        self._engine.reset()
        return 0, ""

    def _run_operations(self, ops) -> tuple[int, tuple[SkippedOperation, ...]]:
        """Re-run ``ops`` in order, skipping and recording whatever cannot run.

        Four distinguishable ways an operation fails to come back, all reported with the
        underlying message rather than a generic label — an agent told *"no object named
        'bad_hole'"* can act, one told *"an operation was skipped"* cannot.
        """
        applied = 0
        skipped: list[SkippedOperation] = []
        for op in ops:
            if op.opaque:
                skipped.append(
                    SkippedOperation(
                        op.op_id,
                        op.kind,
                        "opaque operation: not replayable, and its geometry snapshot "
                        "could not be restored",
                    )
                )
                continue
            handler = self._handlers.get(op.kind)
            if handler is None:
                skipped.append(
                    SkippedOperation(
                        op.op_id, op.kind, f"no handler is registered for kind {op.kind!r}"
                    )
                )
                continue
            try:
                result = handler(self._engine, op)
            except Exception as exc:  # noqa: BLE001 — one dead operation, not a dead session
                skipped.append(SkippedOperation(op.op_id, op.kind, f"{type(exc).__name__}: {exc}"))
                continue
            if not result.ok:
                skipped.append(
                    SkippedOperation(
                        op.op_id,
                        op.kind,
                        result.error_detail or result.error_rule or "the handler reported failure",
                    )
                )
                continue
            applied += 1
        return applied, tuple(skipped)

    def _write_geometry_snapshot(self, label: str) -> str:
        """Capture the live geometry under a name unique within this session.

        The counter matters: an opaque operation needs a *pair* of captures under the same
        op id, and two files that collide are one restore silently reading the other side
        of the barrier.
        """
        self._snapshot_seq += 1
        scene_id = self._document.scene_id or "scene"
        path = snapshot_directory() / f"{scene_id}-{self._snapshot_seq:04d}-{label}.json"
        return capture(self._engine, str(path))

    def _discard_orphans(self, before: set[str]) -> None:
        """Remove anything the failed handler created, leaving the scene as it was found.

        Only objects that did not exist before the attempt are touched, so a handler that
        modified existing geometry before failing is not made worse — that residue is real
        and is reported rather than silently reverted, because reverting a modification
        needs the old geometry and this method does not have it. Deleting what was newly
        created is unambiguous; that is why it is the part that is undone.

        Never raises: this runs on the failure path, and an exception here would replace
        the handler's real error with a cleanup error the agent cannot act on.
        """
        try:
            for object_id in set(self._engine.list_objects()) - before:
                try:
                    self._engine.delete(object_id)
                except Exception:  # noqa: BLE001 — one stubborn object must not stop the rest
                    continue
        except Exception:  # noqa: BLE001 — engine unusable; the original error still stands
            return
