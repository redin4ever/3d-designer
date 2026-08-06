"""Which geometry snapshot describes which point in the log.

An :class:`contracts.UndoBarrier` records that a point *cannot be replayed across*. This
records the only thing that makes that survivable: a file holding the geometry as it stood
at a given log index, so a rebuild can start there instead of at ``engine.reset()``.

Two are kept per opaque operation, and both are needed:

- the state **before** it ran, so undoing back to it lands exactly, and
- the state **after** it ran, so redoing forward past it does not re-execute the script.

A single pre-execution capture is enough to undo and not enough to redo — which is the
half of F-011 that produced ``randobj_8ca638``, ``randobj_9244a7`` and ``randobj_b89aaa``
from one redo of one operation.

Indices are *log positions*, and index ``i`` means "after ``operations[:i]`` have run".
So the barrier for the opaque operation at index ``i`` stores its pre-state at ``i`` and
its post-state at ``i + 1``.
"""

from __future__ import annotations

from typing import Any, Iterator

__all__ = ["SnapshotLedger"]


class SnapshotLedger:
    """Log index → geometry snapshot path, kept honest as the head moves."""

    __slots__ = ("_states",)

    def __init__(self, states: dict[int, str] | None = None) -> None:
        self._states: dict[int, str] = dict(states or {})

    def __len__(self) -> int:
        return len(self._states)

    def __contains__(self, index: int) -> bool:
        return index in self._states

    def register(self, index: int, before: str, after: str) -> None:
        """Record both sides of the opaque operation at log position ``index``."""
        if before:
            self._states[index] = before
        if after:
            self._states[index + 1] = after

    def prune_beyond(self, head: int) -> None:
        """Forget everything past ``head``.

        Called *before* an append that will truncate. After truncation those indices
        describe operations that no longer exist, and index ``n`` silently comes to mean a
        different point in a different log — a restore from one would produce a plausible
        wrong scene, which is the failure mode ``SceneDocument.set_head`` already refuses
        for a negative index.
        """
        self._states = {i: p for i, p in self._states.items() if i <= head}

    def candidates_for(self, head: int) -> Iterator[tuple[int, str]]:
        """Every state that could serve as a base for rebuilding to ``head``, nearest
        first.

        Nearest first because the nearest base replays the fewest operations; *every*
        candidate rather than only the nearest because a snapshot file can be missing —
        temp directories are cleaned, sessions end — and falling back to an earlier one
        beats falling all the way back to a replay that would re-run the opaque code.
        """
        for index in sorted((i for i in self._states if i <= head), reverse=True):
            yield index, self._states[index]

    def to_json(self) -> dict[str, str]:
        """String keys: JSON object keys are strings, and a dict with integer keys
        round-trips as one with string keys whether or not anybody planned it."""
        return {str(index): path for index, path in sorted(self._states.items())}

    @staticmethod
    def from_json(data: Any) -> "SnapshotLedger":
        if not isinstance(data, dict):
            return SnapshotLedger()
        states: dict[int, str] = {}
        for key, path in data.items():
            try:
                states[int(key)] = str(path)
            except (TypeError, ValueError):
                continue
        return SnapshotLedger(states)
