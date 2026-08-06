"""Moving the undo pointer: ``undo``, ``redo``, ``rollback_to``, ``checkpoint`` (ADR-006).

Undo is a pointer move, not a snapshot: every method here ends by calling ``self.replay()``
(see ``document.py``) to rebuild geometry from wherever the pointer now sits, never by
hand-patching engine state. The one thing every method must get right is telling
``ROLLBACK`` apart from ``FULL_RESYNC`` — the difference between an incremental viewer
update and a full reload (see ``contracts.ChangeKind``'s own docstring).

Two additions after the product met real Blender, both visible here and implemented in
``document.py``:

- ``replay`` now returns a :class:`~scene.replay_report.ReplayReport`. Each method below
  forwards its summary to listeners in ``SceneChangeEvent.log_line`` and keeps it on
  ``Scene.last_replay``, because a rebuild that silently dropped operations leaves the
  operator looking at a scene that appears whole (F-010).
- Rebuilding restores from a captured geometry snapshot where one exists, so an opaque
  operation is never re-executed. :meth:`capture_snapshot` is what produces those, and it
  lives here rather than beside ``save``/``load`` because a barrier is an undo concept:
  ADR-006's "undo across one is a snapshot restore, not a replay" is this file's sentence.
"""

from __future__ import annotations

from contracts import ChangeKind, Checkpoint, SceneChangeEvent

from .replay_report import ReplayReport

__all__ = ["HistoryMixin"]


class HistoryMixin:
    """``undo``/``redo``/``rollback_to``/``checkpoint``/``capture_snapshot``. See
    ``document.py``'s docstring for what ``self`` is expected to carry."""

    def undo(self, steps: int = 1) -> ChangeKind:
        """Move the head back ``steps`` operations and rebuild geometry.

        1. ``old_head = self._document.head``; ``new_head = old_head - steps``.
        2. ``self._document.set_head(new_head)`` — let whatever it raises propagate
           unchanged. **Chosen policy: undo past the beginning raises; it does not
           clamp** (``SceneDocument.set_head``'s own ``ValueError`` does this for free).
           A clamp would silently turn "undo 5" into "undo 2" with no signal to the
           caller that fewer steps happened than asked — the same silent-wrong-answer
           shape ``set_head``'s own docstring already rejects for a raw negative index.
           See ``history_test.py::test_undo_past_the_beginning_raises``.
        3. A barrier was crossed iff any ``b`` in ``self._document.barriers`` has
           ``new_head <= b.index < old_head`` — an opaque operation that was active is
           now undone. Use ``ChangeKind.FULL_RESYNC`` if so, ``ChangeKind.ROLLBACK``
           otherwise.
        4. ``self.replay()``.
        5. Emit one ``contracts.SceneChangeEvent(kind=<that ChangeKind>,
           head=self._document.head)`` via ``self._emit`` and return the ``ChangeKind``.
        """
        old_head = self._document.head
        new_head = old_head - steps
        self._document.set_head(new_head)
        crossed = any(new_head <= b.index < old_head for b in self._document.barriers)
        kind = ChangeKind.FULL_RESYNC if crossed else ChangeKind.ROLLBACK
        self._emit_rebuild(kind, self.replay())
        return kind

    def redo(self, steps: int = 1) -> ChangeKind:
        """The mirror of :meth:`undo`: ``new_head = self._document.head + steps``, the
        same ``set_head`` call — so redo past the end of the log raises for the identical
        reason. This matters in particular after a truncating ``apply``: once the undone
        tail has been dropped for good, ``new_head`` is out of range and this is exactly
        how that becomes visible, rather than redo silently doing nothing while the
        caller believes it worked. A barrier is crossed iff any ``b`` has
        ``old_head <= b.index < new_head``. Same ``replay`` + emit + return shape as
        :meth:`undo`.
        """
        old_head = self._document.head
        new_head = old_head + steps
        self._document.set_head(new_head)
        crossed = any(old_head <= b.index < new_head for b in self._document.barriers)
        kind = ChangeKind.FULL_RESYNC if crossed else ChangeKind.ROLLBACK
        self._emit_rebuild(kind, self.replay())
        return kind

    def rollback_to(self, checkpoint: str) -> ChangeKind:
        """Move the head directly to a named checkpoint, in either direction.

        ``cp = self._document.checkpoint(checkpoint)`` — propagate its ``KeyError``
        unchanged for an unknown name; it already names the checkpoints that do exist. A
        barrier is crossed iff any ``b.index`` lies in
        ``[min(head, cp.index), max(head, cp.index))``. Then
        ``self._document.set_head(cp.index)``, ``self.replay()``, emit, return — the
        identical shape to :meth:`undo`/:meth:`redo`.
        """
        cp = self._document.checkpoint(checkpoint)
        old_head = self._document.head
        lo, hi = min(old_head, cp.index), max(old_head, cp.index)
        crossed = any(lo <= b.index < hi for b in self._document.barriers)
        kind = ChangeKind.FULL_RESYNC if crossed else ChangeKind.ROLLBACK
        self._document.set_head(cp.index)
        self._emit_rebuild(kind, self.replay())
        return kind

    def capture_snapshot(self, op_id: str) -> str:
        """Write the live **geometry** to a restorable file and return its path.

        See ``contracts.ScenePort.capture_snapshot`` for why this exists and why it must
        not be ``save()``. Called immediately before an opaque operation, because that is
        the only moment the pre-execution state still exists — ``apply`` takes its own
        capture at that same moment if the path it is handed turns out not to be one of
        these, so a caller that gets it wrong degrades rather than silently loses the
        barrier.
        """
        return self._write_geometry_snapshot(f"{op_id}.before")

    @property
    def last_replay(self) -> ReplayReport:
        """What the most recent rebuild managed.

        A property rather than a return value on :meth:`undo` because those three methods
        return a ``ChangeKind`` that ``viewer`` switches on, and widening it would change
        a contract sixteen modules read. The event's ``log_line`` carries the same summary
        for anyone listening rather than asking.
        """
        return self._last_replay

    def checkpoint(self, name: str, note: str = "") -> Checkpoint:
        """Name the current head.

        A thin wrap over ``self._document.add_checkpoint(name, note)`` — propagate its
        ``ValueError`` for a duplicate name unchanged — that also emits one
        ``contracts.SceneChangeEvent(kind=ChangeKind.CHECKPOINT,
        head=self._document.head)`` via ``self._emit`` before returning the new
        ``Checkpoint``.
        """
        cp = self._document.add_checkpoint(name, note)
        self._emit(SceneChangeEvent(kind=ChangeKind.CHECKPOINT, head=self._document.head))
        return cp

    def _emit_rebuild(self, kind: ChangeKind, report: ReplayReport) -> None:
        """One event per history move, carrying what the rebuild could not do.

        ``log_line`` stays empty on the ordinary path so that a non-empty one means
        something actually happened — a line on every event is a line nobody reads by the
        time it matters.
        """
        self._emit(
            SceneChangeEvent(
                kind=kind,
                head=self._document.head,
                log_line="" if report.complete and not report.restored_from else report.describe(),
            )
        )
