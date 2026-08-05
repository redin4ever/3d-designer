"""The scene document, checkpoints, and the change event the live view subscribes to.

The document's invariants are enforced by its own methods rather than described in
comments. Every one below was reachable in an earlier draft by appending to a public list:
a negative ``head`` silently dropped the last operation instead of raising, an opaque
operation could exist with no matching undo barrier, and appending after an undo left the
undone operations in place to be replayed later in the wrong order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .geometry import MeshSnapshot
from .operations import Operation
from .phases import CheckCadence, LockContention, Phase, WriteLease

__all__ = [
    "SceneDocument",
    "Checkpoint",
    "ChangeKind",
    "SceneChangeEvent",
    "UndoBarrier",
    "SCHEMA_VERSION",
]

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A named pointer into the operation log.

    A checkpoint costs one integer, not a copy of the scene — the only reason per-action
    undo is affordable at thousands of objects (ADR-006, ADR-011).
    """

    name: str
    index: int
    phase: Phase
    note: str = ""


@dataclass(frozen=True, slots=True)
class UndoBarrier:
    """A point in the log that cannot be replayed across.

    Raw code execution and any opaque mesh edit create one. Rolling back past a barrier
    needs a snapshot restore rather than a replay, so ``snapshot_path`` is **required**:
    a barrier without one is a rollback that discovers at the moment of use that it has
    nothing to restore from.
    """

    index: int
    op_id: str
    reason: str
    snapshot_path: str

    def __post_init__(self) -> None:
        if not self.snapshot_path:
            raise ValueError(
                f"undo barrier at op {self.op_id!r} has no snapshot path. Capture the "
                "snapshot first — a barrier is only useful if it can be restored from."
            )


@dataclass
class SceneDocument:
    """The source of truth. Geometry is generated from this, never the reverse.

    Mutable, and owned exclusively by ``src/scene/``; every other module reads it through
    that module's public interface. Mutate it through the methods below rather than
    touching the lists directly — that is what keeps the invariants true.
    """

    schema_version: int = SCHEMA_VERSION
    scene_id: str = ""
    unit_scale: float = 1.0
    """Metres per unit. Locked at 1.0 by default and changeable per scene (Gate A 6.2).
    Every downstream dimension check is meaningless if this drifts silently between
    assets, so ingest converts rather than adopting an incoming scale."""

    operations: list[Operation] = field(default_factory=list)
    head: int = 0
    """Undo pointer. Operations at index >= head are undone but retained, so redo is also
    a pointer move. Appending truncates them — see :meth:`append`."""

    checkpoints: list[Checkpoint] = field(default_factory=list)
    barriers: list[UndoBarrier] = field(default_factory=list)
    phase: Phase = Phase.BLOCKOUT
    check_cadence: CheckCadence = CheckCadence.EVERY_GEOMETRY_CHANGE
    """Persisted here so a mid-run cadence change survives, rather than living in some
    module's private state under a key nobody else knows."""

    active_lease: WriteLease | None = None
    """The single write lock (ADR-007). One field, one truth. A lease value held by an
    agent means nothing unless it is *this* one."""

    engine_backend: str = ""
    """Which engine produced the current evaluation, e.g. ``bpy-5.2.0``. Recorded so a
    reader can tell whether a result came from real Blender or a fake."""

    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ reading

    @property
    def active_count(self) -> int:
        """Number of applied operations. Prefer this over ``len(active_operations)`` —
        that property copies, and on a level with tens of thousands of log entries a
        per-call copy turns every tool call into O(head) work."""
        return self.head

    @property
    def active_operations(self) -> list[Operation]:
        """A copy of the applied operations. O(head) — do not call it to get a count."""
        return self.operations[: self.head]

    def barrier_before(self, index: int) -> UndoBarrier | None:
        """The nearest barrier at or after ``index`` — the one that makes rolling back to
        ``index`` a restore rather than a replay."""
        candidates = [b for b in self.barriers if b.index >= index]
        return min(candidates, key=lambda b: b.index) if candidates else None

    # ------------------------------------------------------------------ writing

    def append(self, op: Operation, *, snapshot_path: str = "") -> None:
        """Append an operation, truncating anything previously undone.

        Truncation is not optional. Leaving undone operations in place means a later redo
        replays stale work ahead of the new operation, corrupting the very order the
        replay model depends on.
        """
        if any(existing.op_id == op.op_id for existing in self.operations):
            raise ValueError(
                f"operation id {op.op_id!r} is already in the log. Ids key the geometry "
                "cache, so a duplicate silently overwrites an earlier result."
            )
        if self.head < len(self.operations):
            dropped = self.operations[self.head :]
            self.operations = self.operations[: self.head]
            self.barriers = [b for b in self.barriers if b.index < self.head]
            self.checkpoints = [c for c in self.checkpoints if c.index <= self.head]
            del dropped
        if op.opaque and not snapshot_path:
            raise ValueError(
                f"operation {op.op_id!r} is opaque but no snapshot path was given. An "
                "opaque operation cannot be replayed, so rolling back across it needs a "
                "snapshot — capture one before appending."
            )
        self.operations.append(op)
        self.head = len(self.operations)
        if op.opaque:
            self.barriers.append(
                UndoBarrier(
                    index=len(self.operations) - 1,
                    op_id=op.op_id,
                    reason=f"{op.kind} is not replayable",
                    snapshot_path=snapshot_path,
                )
            )

    def set_head(self, index: int) -> None:
        """Move the undo pointer, with bounds enforced.

        A negative index would slice from the end and silently drop the last operation
        instead of raising — an undo that produces a plausible wrong scene rather than an
        error.
        """
        if not 0 <= index <= len(self.operations):
            raise ValueError(
                f"head {index} is outside 0..{len(self.operations)}"
            )
        self.head = index

    def add_checkpoint(self, name: str, note: str = "") -> Checkpoint:
        if any(c.name == name for c in self.checkpoints):
            raise ValueError(f"checkpoint {name!r} already exists")
        cp = Checkpoint(name=name, index=self.head, phase=self.phase, note=note)
        self.checkpoints.append(cp)
        return cp

    def checkpoint(self, name: str) -> Checkpoint:
        for c in self.checkpoints:
            if c.name == name:
                return c
        known = ", ".join(c.name for c in self.checkpoints) or "(none)"
        raise KeyError(f"no checkpoint named {name!r}; known: {known}")

    def require_lease(self, lease: WriteLease) -> None:
        """Raise unless ``lease`` is the live write lock."""
        live = self.active_lease
        if live is None:
            raise LockContention(holder="(none)", expires_at_op=self.head)
        if live.lease_id != lease.lease_id:
            raise LockContention(holder=live.holder, expires_at_op=live.expires_at_op)


class ChangeKind(StrEnum):
    OBJECTS_ADDED = "objects_added"
    OBJECTS_MODIFIED = "objects_modified"
    OBJECTS_REMOVED = "objects_removed"
    TRANSFORMS_ONLY = "transforms_only"
    """Cheapest update — the viewer patches node transforms and touches no buffers."""

    TOPOLOGY_CHANGED = "topology_changed"
    """Vertex/index counts changed, so cached buffers are invalid and must be resent."""

    ROLLBACK = "rollback"
    """An undo or redo that did not cross a barrier. The viewer applies it as a normal
    add/remove/modify diff. Named explicitly because leaving it undefined invites
    ``scene`` to send a full resync while ``viewer`` waits for an incremental update that
    never arrives."""

    FULL_RESYNC = "full_resync"
    """Discard everything and reload. Emitted after an opaque edit, an undo across a
    barrier, or any state the diff protocol cannot express. Not a nicety — there is no
    production-ready incremental glTF/USD streaming format, so this is the correctness
    path the fast path degrades to."""

    PHASE_CHANGED = "phase_changed"
    CHECKPOINT = "checkpoint"


@dataclass(frozen=True, slots=True)
class SceneChangeEvent:
    """What ``src/scene/`` emits and ``src/viewer/`` subscribes to.

    ``scene`` never imports ``viewer``. The dependency arrow points from the web layer
    into the core and never back, which lets the viewer be disabled, rebuilt or crash
    without touching geometry logic.
    """

    kind: ChangeKind
    op_id: str = ""
    object_ids: tuple[str, ...] = ()
    snapshots: tuple[MeshSnapshot, ...] = ()
    """Populated only for kinds needing buffers. Empty on ``TRANSFORMS_ONLY``, which is
    the common case and the reason it is cheap."""

    highlight: tuple[str, ...] = ()
    """Objects the viewer should pick out as "what just changed" (Gate A 5.3)."""

    phase: Phase | None = None
    log_line: str = ""
    head: int = 0
