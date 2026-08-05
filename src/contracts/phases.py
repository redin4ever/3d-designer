"""Phases, the single write lock, conflicts, and check cadence.

ADR-007: phase gating *is* the concurrency-control mechanism, not a separate thing that
cooperates with one. A live 3D scene is shared mutable state — the case where parallel
LLM writers are measured to make conflicting implicit decisions and corrupt each other's
work. Many sub-agents read and propose; exactly one writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .measurement import AcceptanceQuery, Defect

__all__ = [
    "Phase",
    "PHASE_ORDER",
    "CheckCadence",
    "RunState",
    "WriteLease",
    "Proposal",
    "Conflict",
    "PhasePromotion",
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
    setting exists because the user asked for it, not as an escape.
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


@dataclass(frozen=True, slots=True)
class WriteLease:
    """Proof that a given agent currently holds the single write lock."""

    holder: str
    phase: Phase
    lease_id: str
    granted_at_op: int


@dataclass(frozen=True, slots=True)
class Proposal:
    """A change a read-only sub-agent wants made.

    Inspect-role agents cannot write. They measure, critique, and return one of these;
    the writer applies it. This is the mechanism by which parallelism is real without
    concurrent mutation.
    """

    proposal_id: str
    author: str
    target_objects: tuple[str, ...]
    operation_kind: str
    params: dict = field(default_factory=dict)
    rationale: str = ""
    supporting_defects: tuple[Defect, ...] = ()


@dataclass(frozen=True, slots=True)
class Conflict:
    """Two proposals that cannot both be applied.

    Surfaced with the exact geometry involved, like a merge conflict, and never resolved
    silently (Gate A 10.3). Last-writer-wins is specifically wrong here: for geometry, a
    silent overwrite produces an invalid model rather than a surprise — one agent moving
    a wall while another attaches a railing to it.
    """

    conflict_id: str
    proposals: tuple[Proposal, ...]
    overlapping_objects: tuple[str, ...]
    detail: str
    magnitude: float = 0.0
    unit: str = "m"

    def describe(self) -> str:
        authors = ", ".join(p.author for p in self.proposals)
        mag = f" ({self.magnitude:.4g}{self.unit})" if self.magnitude else ""
        return (
            f"CONFLICT {self.conflict_id}: {authors} both touch "
            f"{', '.join(self.overlapping_objects)}{mag} — {self.detail}"
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
