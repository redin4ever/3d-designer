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

from .errors import RuleError
from .geometry import Vec3
from .measurement import AcceptanceQuery, Defect
from .operations import Proposal, ToolRole

__all__ = [
    "Phase",
    "PHASE_ORDER",
    "PHASE_ROLES",
    "ALWAYS_LEGAL_ROLES",
    "roles_for_phase",
    "CheckCadence",
    "RunState",
    "WriteLease",
    "WriteLockManager",
    "LockContention",
    "PhaseViolation",
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


ALWAYS_LEGAL_ROLES: tuple[ToolRole, ...] = (ToolRole.INSPECT, ToolRole.ADMIN)
"""Legal in every phase. ``INSPECT`` is read-only and cannot corrupt an ordering; ``ADMIN``
owns checkpoints, rollback and raw execution, which are exactly the tools an agent needs
when it has got itself stuck — locking them behind a phase would wedge the run."""


PHASE_ROLES: dict[Phase, tuple[ToolRole, ...]] = {
    Phase.BLOCKOUT: (ToolRole.BLOCKOUT,),
    Phase.REFINE: (ToolRole.BLOCKOUT, ToolRole.REFINE, ToolRole.REPAIR, ToolRole.ALIGN),
    Phase.DETAIL: (ToolRole.DETAIL, ToolRole.REPAIR, ToolRole.ALIGN),
    Phase.POLISH: (ToolRole.POLISH, ToolRole.EXPORT, ToolRole.REPAIR, ToolRole.ALIGN),
}
"""Which roles may act in each phase (ADR-013).

Until Gate B this table did not exist and ``dispatch`` checked only the role string the
caller itself supplied, never comparing it to the session's phase — so a POLISH tool
(``unwrap_uvs``) and a REFINE tool (``add_railing``) both succeeded silently while the
session had never left ``blockout``. The staged plan was advisory in the strictest sense.

Two deliberate asymmetries, both load-bearing:

- **``REPAIR`` and ``ALIGN`` are legal from ``REFINE`` onward, not just in ``REFINE``.**
  ADR-012 removed the promotion override, so a detail-phase operation that introduces a
  non-manifold edge would otherwise produce a phase that can never pass its own acceptance
  query and can never be left. Fixing what you just broke must not require going backwards.
- **``BLOCKOUT`` is legal in ``REFINE``.** Realising you forgot a wall is normal; forcing a
  demotion for it would make the gate an obstacle rather than a check.

What this actually refuses is the ordering the review found broken: detailing or polishing
geometry whose shape is not settled yet.
"""


def roles_for_phase(phase: Phase) -> tuple[ToolRole, ...]:
    """Every role legal in ``phase``, including the always-legal ones."""
    return PHASE_ROLES.get(phase, ()) + ALWAYS_LEGAL_ROLES


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


class LockContention(RuleError):
    """Someone else holds the write lock.

    A named error rather than a bare ``RuntimeError`` because an agent that is told
    *who* holds the lock and *when it expires* can wait usefully; one given a traceback
    retries immediately, forever.
    """

    def __init__(self, holder: str, expires_at_op: int) -> None:
        super().__init__(
            rule="orchestration.lock_contention",
            detail=f"write lock held by {holder!r} until operation {expires_at_op}",
            suggestion=(
                f"wait for operation {expires_at_op}, or acquire an INSPECT role, which "
                "needs no write lease and may run concurrently"
            ),
        )
        self.holder = holder
        self.expires_at_op = expires_at_op


class PhaseViolation(RuleError):
    """A tool was called that its caller's role does not hold, or that is not legal in the
    session's current phase (ADR-013).

    The message must name the phase, the tool, the role that would allow it, and how to
    promote. A refusal that says only "not allowed" makes an agent retry the same call,
    which is the failure Gate A 4.2 was asked about — and, since ADR-012 removed the
    promotion override, an agent that cannot work out how to move forward has no escape.
    """

    def __init__(
        self,
        tool: str,
        held: tuple[ToolRole, ...],
        phase: Phase,
        *,
        required: tuple[ToolRole, ...] = (),
    ) -> None:
        legal = roles_for_phase(phase)
        need = ", ".join(sorted(r.value for r in required)) or "(none declared)"
        super().__init__(
            rule="orchestration.phase_violation",
            detail=(
                f"tool {tool!r} needs role {need}; this lease holds "
                f"{', '.join(sorted(r.value for r in held)) or '(none)'} "
                f"and the session is in phase {phase.value!r}"
            ),
            suggestion=(
                f"roles legal in {phase.value}: {', '.join(sorted(r.value for r in legal))}. "
                "Call promote_phase when this phase's acceptance queries pass, or acquire "
                "a lease with the role you need."
            ),
        )
        self.tool = tool
        self.held = held
        self.phase = phase
        self.required = required


@dataclass(frozen=True, slots=True)
class WriteLease:
    """Proof that a given agent currently holds the single write lock, and of what it may do.

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

    roles: tuple[ToolRole, ...] = ()
    """The roles this lease grants (ADR-013).

    **This is the authority, not the role string a caller passes with a call.** Before
    Gate B, ``dispatch`` read the role from the request itself, so an agent could claim any
    role simply by saying so. The role now travels with the lease the lock manager issued,
    and a request's own claim is ignored.

    Empty means every role legal in :attr:`phase` — the ordinary case for a single-agent
    session, where partitioning buys nothing. A multi-agent run narrows it per agent.

    This is a coordination mechanism, not a security boundary: ADR-009 gives every
    connected agent arbitrary code execution by explicit user choice, and no role check
    contains that.
    """

    def is_stale(self, current_op: int) -> bool:
        return current_op >= self.expires_at_op

    def granted_roles(self) -> tuple[ToolRole, ...]:
        """The effective role set: what was granted, narrowed to what the phase allows."""
        legal = roles_for_phase(self.phase)
        if not self.roles:
            return legal
        return tuple(r for r in self.roles if r in legal)

    def permits(self, roles: tuple[ToolRole, ...]) -> bool:
        """True if any of ``roles`` — a tool's declared roles — is currently held."""
        granted = set(self.granted_roles())
        return any(r in granted for r in roles)


@runtime_checkable
class WriteLockManager(Protocol):
    """The single-writer mechanism, declared rather than merely described.

    ADR-007's guarantee is the load-bearing safety property of the whole multi-agent
    design, and several modules need to ask about it: ``mcp`` gating a mutating call,
    ``raw`` before an opaque execution, ``viewer`` showing lock status.
    """

    def acquire(
        self,
        holder: str,
        phase: Phase,
        *,
        ttl_ops: int = 64,
        roles: tuple[ToolRole, ...] = (),
    ) -> WriteLease:
        """Raises :class:`LockContention` if a live lease is held by someone else.

        ``roles`` narrows what the returned lease permits; empty grants everything legal
        in ``phase``. The lease is where role authority lives (ADR-013) — a caller cannot
        widen it afterwards, because :class:`WriteLease` is frozen and only the manager
        issues one.
        """
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

    **There is no override** (ADR-012, Gate B 1.1). The ``allow_override`` field this type
    used to carry is gone, and so is ``promote(force=True)``. What shipped in pass 1 was
    neither: it promoted whenever the phase had recorded any operation at all, so the
    queries here were declared and never evaluated.

    The consequence is that a failing query must be *actionable*. Every
    :class:`~contracts.measurement.AcceptanceResult` it produces names the subject, the
    measured value, the threshold and the operation that would fix it, because an agent
    that cannot pass and cannot force has nothing else to work from.
    """

    from_phase: Phase
    to_phase: Phase
    queries: tuple[AcceptanceQuery, ...] = ()

    def __post_init__(self) -> None:
        if not self.queries:
            raise ValueError(
                f"promotion {self.from_phase.value} -> {self.to_phase.value} declares no "
                "acceptance queries. Since ADR-012 removed the override, a promotion with "
                "nothing to check is a promotion that checks nothing and cannot be refused "
                "— which is exactly the placeholder behaviour that ADR replaced."
            )
