"""Stub — moving the undo pointer: ``undo``, ``redo``, ``rollback_to``, ``checkpoint``
(ADR-006).

Undo is a pointer move, not a snapshot: every method here ends by calling
``self.replay()`` (see ``document.py``) to rebuild geometry from wherever the pointer now
sits, never by hand-patching engine state. The one thing every method must get right is
telling ``ROLLBACK`` apart from ``FULL_RESYNC`` — the difference between an incremental
viewer update and a full reload (see ``contracts.ChangeKind``'s own docstring).

Nothing here is implemented yet.
"""

from __future__ import annotations

from contracts import ChangeKind, Checkpoint

__all__ = ["HistoryMixin"]

_NOT_IMPLEMENTED = "scene.{name}: not implemented"


class HistoryMixin:
    """``undo``/``redo``/``rollback_to``/``checkpoint``. See ``document.py``'s docstring
    for what ``self`` is expected to carry."""

    def undo(self, steps: int = 1) -> ChangeKind:
        """Move the head back ``steps`` operations and rebuild geometry.

        Once implemented:

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
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="undo"))

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
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="redo"))

    def rollback_to(self, checkpoint: str) -> ChangeKind:
        """Move the head directly to a named checkpoint, in either direction.

        Once implemented: ``cp = self._document.checkpoint(checkpoint)`` — propagate its
        ``KeyError`` unchanged for an unknown name; it already names the checkpoints that
        do exist. A barrier is crossed iff any ``b.index`` lies in
        ``[min(head, cp.index), max(head, cp.index))``. Then
        ``self._document.set_head(cp.index)``, ``self.replay()``, emit, return — the
        identical shape to :meth:`undo`/:meth:`redo`.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="rollback_to"))

    def checkpoint(self, name: str, note: str = "") -> Checkpoint:
        """Name the current head.

        A thin wrap over ``self._document.add_checkpoint(name, note)`` — propagate its
        ``ValueError`` for a duplicate name unchanged — that also emits one
        ``contracts.SceneChangeEvent(kind=ChangeKind.CHECKPOINT,
        head=self._document.head)`` via ``self._emit`` before returning the new
        ``Checkpoint``.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="checkpoint"))
