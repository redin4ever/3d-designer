"""The scene document, checkpoints, and the change event the live view subscribes to."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .geometry import MeshSnapshot
from .operations import Operation

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

    A checkpoint costs one integer, not a copy of the scene — which is the only reason
    per-action undo is affordable at thousands of objects (ADR-006, ADR-011).
    """

    name: str
    index: int
    phase: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class UndoBarrier:
    """A point in the log that cannot be replayed across.

    Raw code execution and any opaque mesh edit create one. Rolling back past a barrier
    requires a snapshot restore rather than a replay, and this type is what makes that
    cost visible at the moment it is incurred instead of discovered later.
    """

    index: int
    op_id: str
    reason: str
    snapshot_path: str = ""


@dataclass
class SceneDocument:
    """The source of truth. Geometry is generated from this, never the reverse.

    Mutable by design and owned exclusively by ``src/scene/``; every other module reads
    it through that module's public interface.
    """

    schema_version: int = SCHEMA_VERSION
    scene_id: str = ""
    unit_scale: float = 1.0
    """Metres per unit. Locked at 1.0 by default and changeable per scene (Gate A 6.2).
    Every real-world dimension check downstream is meaningless if this drifts silently
    between assets, so ingest converts rather than adopting an incoming scale."""

    operations: list[Operation] = field(default_factory=list)
    head: int = 0
    """Undo pointer. Operations at index >= head are undone but retained, so redo is also
    a pointer move. Appending a new operation truncates them."""

    checkpoints: list[Checkpoint] = field(default_factory=list)
    barriers: list[UndoBarrier] = field(default_factory=list)
    phase: str = "blockout"
    engine_backend: str = ""
    """Which engine produced the current evaluation, e.g. ``bpy-5.2.0``. Recorded so a
    reader can tell whether a result came from real Blender or a fake."""

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def active_operations(self) -> list[Operation]:
        return self.operations[: self.head]

    def barrier_before(self, index: int) -> UndoBarrier | None:
        """The nearest barrier at or after ``index`` — i.e. the one that makes rolling
        back to ``index`` a restore rather than a replay."""
        candidates = [b for b in self.barriers if b.index >= index]
        return min(candidates, key=lambda b: b.index) if candidates else None


class ChangeKind(StrEnum):
    OBJECTS_ADDED = "objects_added"
    OBJECTS_MODIFIED = "objects_modified"
    OBJECTS_REMOVED = "objects_removed"
    TRANSFORMS_ONLY = "transforms_only"
    """Cheapest update — the viewer patches node transforms and touches no buffers."""

    TOPOLOGY_CHANGED = "topology_changed"
    """Vertex/index counts changed, so cached buffers are invalid and must be resent."""

    FULL_RESYNC = "full_resync"
    """The viewer must discard everything and reload. Emitted after an opaque edit, an
    undo across a barrier, or any state the diff protocol cannot express. There is no
    production-ready incremental glTF/USD streaming format, so this fallback is not
    optional — it is the correctness path the fast path falls back to."""

    PHASE_CHANGED = "phase_changed"
    CHECKPOINT = "checkpoint"


@dataclass(frozen=True, slots=True)
class SceneChangeEvent:
    """What ``src/scene/`` emits and ``src/viewer/`` subscribes to.

    ``scene`` never imports ``viewer``. The dependency arrow points from the web layer
    into the core and never back, which is what lets the viewer be disabled, rebuilt or
    crash without touching geometry logic.
    """

    kind: ChangeKind
    op_id: str = ""
    object_ids: tuple[str, ...] = ()
    snapshots: tuple[MeshSnapshot, ...] = ()
    """Populated only for kinds the viewer needs buffers for. Empty on
    ``TRANSFORMS_ONLY``, which is the common case and the reason it is cheap."""

    highlight: tuple[str, ...] = ()
    """Objects the viewer should pick out as "what just changed" (Gate A 5.3)."""

    phase: str = ""
    log_line: str = ""
    """One line for the action log, already formatted."""

    head: int = 0
