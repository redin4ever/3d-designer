"""Phases, the single write lock, conflicts, and check cadence.

ADR-007: phase gating *is* the concurrency-control mechanism, not a separate thing that
cooperates with one. A live 3D scene is shared mutable state — the case where parallel
LLM writers are measured to make conflicting implicit decisions and corrupt each other's
work. Many sub-agents read and propose; exactly one writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .geometry import Vec3
from .measurement import AcceptanceQuery, Defect
from .operations import Proposal

__all__ = [
    "Phase",
    "PHASE_ORDER",
    "CheckCadence",
    "RunState",
    "WriteLease",
    "WriteLockManager",
    "LockContention",
    "Conflict",
    "PhasePromotion",
    "Proposal",
]


class Phase(StrEnum):
    """The professional progression, and the reason human work does not look like glued
    boxes: blockout is *supposed* to be boxes, and every later pass exists to convert
    them. Today's AI 3D tools skip the middle, which is the structural reason for the
    "stitched together" complaint this product exists to answer."""

    BLOCKOUT = "blockout"
    """Primitives, proportion, placement. No detail. Deliberately boxes."""

    REFINE = "refine"
    """Correct topology, close gaps, resolve clipping, fix alignment."""

    DETAIL = "detail"
    """Bevels, panel lines, greebles, material variation."""

    POLISH = "polish"
    """UV, bake, LODs, budget, export readiness."""


PHASE_ORDER: tuple[Phase, ...] = (Phase.BLOCKOUT, Phase.REFINE, Phase.DETAIL, Phase.POLISH)


class CheckCadence(StrEnum):
    """How often geometry is verified.

    Gate A 3.1, verbatim: *"after every change that touches geometry with a settings menu
    setting that enables me changing that"*. The default is the strictest option; the
    setting exists because the user asked for it, not as an escape hatch.
    """

    EVERY_GEOMETRY_CHANGE = "every_geometry_change"
    PHASE_BOUNDARIES = "phase_boundaries"
    ON_REQUEST = "on_request"


class RunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    """Cooperative — checked between operations, never mid-operation, so the log is never
    truncated to a half-applied state (ADR-006)."""

    BLOCKED = "blocked"


class LockContention(RuntimeError):
    """Someone else holds the write lock.

    A named error rather than a bare ``RuntimeError`` because an agent that is told
    *who* holds the lock and *when it expires* can wait usefully; one given a traceback
    retries immediately, forever.
    """

    def __init__(self, holder: str, expires_at_op: int) -> None:
        super().__init__(
            f"write lock held by {holder!r} until operation {expires_at_op}"
        )
        self.rule = "orchestration.lock_contention"
        self.holder = holder
        self.expires_at_op = expires_at_op


@dataclass(frozen=True, slots=True)
class WriteLease:
    """Proof that a given agent currently holds the single write lock.

    Held in exactly one place — ``SceneDocument.active_lease`` — because a lease that can
    be freely constructed proves nothing. Two agents each holding a ``WriteLease`` value
    they built themselves is not a lock; it is two agents with the same dataclass.
    """

    holder: str
    phase: Phase
    lease_id: str
    granted_at_op: int
    expires_at_op: int
    """Operation index past which this lease is stale and may be reclaimed. Without an
    expiry, an agent that dies mid-operation holds the lock forever and the run wedges —
    and agents die (Rule 6)."""

    def is_stale(self, current_op: int) -> bool:
        return current_op >= self.expires_at_op


@runtime_checkable
class WriteLockManager(Protocol):
    """The single-writer mechanism, declared rather than merely described.

    ADR-007's guarantee is the load-bearing safety property of the whole multi-agent
    design, and several modules need to ask about it: ``mcp`` gating a mutating call,
    ``raw`` before an opaque execution, ``viewer`` showing lock status.
    """

    def acquire(self, holder: str, phase: Phase, *, ttl_ops: int = 64) -> WriteLease:
        """Raises :class:`LockContention` if a live lease is held by someone else."""
        ...

    def release(self, lease: WriteLease) -> None: ...

    def current(self) -> WriteLease | None: ...

    def verify(self, lease: WriteLease) -> None:
        """Raise unless ``lease`` is the live one. Called before every mutation."""
        ...


@dataclass(frozen=True, slots=True)
class Conflict:
    """Two or more proposals that cannot both be applied.

    Surfaced with the exact geometry involved, like a merge conflict, and never resolved
    silently (Gate A 10.3). Last-writer-wins is specifically wrong here: for geometry, a
    silent overwrite produces an invalid model rather than a surprise — one agent moving
    a wall while another attaches a railing to it.
    """

    conflict_id: str
    proposals: tuple[Proposal, ...]
    overlapping_objects: tuple[str, ...]
    detail: str
    location: Vec3 | None = None
    """Where in the scene the clash is, so the viewer can point at it rather than
    highlighting whole objects and leaving the operator to find the overlap."""

    defects: tuple[Defect, ...] = ()
    magnitude: float | None = None
    unit: str = "m"

    def __post_init__(self) -> None:
        if len(self.proposals) < 2:
            raise ValueError(
                f"conflict {self.conflict_id!r} has {len(self.proposals)} proposal(s); "
                "a conflict is between at least two"
            )
        if not self.overlapping_objects:
            raise ValueError(
                f"conflict {self.conflict_id!r} names no objects — the operator would be "
                "shown a clash with no geometry attached"
            )

    def describe(self) -> str:
        authors = ", ".join(p.author for p in self.proposals)
        mag = f" ({self.magnitude:.4g}{self.unit})" if self.magnitude is not None else ""
        where = f" at {self.location.as_tuple()}" if self.location else ""
        return (
            f"CONFLICT {self.conflict_id}: {authors} both touch "
            f"{', '.join(self.overlapping_objects)}{mag}{where} — {self.detail}"
        )


@dataclass(frozen=True, slots=True)
class PhasePromotion:
    """Whether a phase may hand off.

    A phase completes when its acceptance queries pass against live geometry — never when
    an agent says it is finished. Agents self-report false success in 13-89% of failures,
    and a second agent reviewing that claim catches it at barely above chance.
    """

    from_phase: Phase
    to_phase: Phase
    queries: tuple[AcceptanceQuery, ...] = ()
    allow_override: bool = True
    """The user chose report-over-block (Gate A 6.3), so promotion can be forced. Forcing
    is recorded in the log; it is not silent."""
