"""Operations, joinery intent, and the MCP tool declaration shape.

An *operation* is one typed, parametric, validated unit of work with a re-runnable
acceptance query. Operations are neither primitives (``add_cube`` — a railing takes ~140
of them and drift accumulates over that distance) nor whole-object composites
(``build("a staircase")`` — measured at -12.6% Exec@1 because the model must get a dozen
parameters right at once with no intermediate check). ADR-004.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from .constraints import ConstraintSet
from .measurement import AcceptanceQuery, Defect, Measurement

__all__ = [
    "OperationStatus",
    "JoineryIntent",
    "Operation",
    "OperationResult",
    "ActionReport",
    "ToolRole",
    "ToolSpec",
    "ToolError",
]


class OperationStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    UNDONE = "undone"


@dataclass(frozen=True, slots=True)
class JoineryIntent:
    """Declared intent that makes an intersection legal.

    No library on earth can distinguish a post socketed 50mm into a deck (correct) from
    two posts overlapping by 50mm (a bug) — both are identical BVH overlaps of identical
    magnitude. The difference is design intent, and intent cannot be inferred from
    geometry. It must be authored.

    Without one of these, any inter-object overlap is a ``PART_CLIPPING`` defect.
    """

    object_id: str
    into_object_id: str
    depth: float
    tolerance: float = 1e-3
    reason: str = ""

    def permits(self, overlap: float) -> bool:
        return overlap <= self.depth + self.tolerance


@dataclass(frozen=True, slots=True)
class Operation:
    """One entry in the scene document's ordered log.

    The log is the source of truth; geometry is generated from it. This is what makes
    undo a pointer move rather than a snapshot restore, and what keeps constraints live.
    """

    op_id: str
    kind: str
    """The operation name, e.g. ``add_railing``. Matches a registered ToolSpec."""

    params: dict[str, Any] = field(default_factory=dict)
    placements: tuple[ConstraintSet, ...] = ()
    joinery: tuple[JoineryIntent, ...] = ()
    acceptance: tuple[AcceptanceQuery, ...] = ()
    phase: str = "blockout"
    author: str = ""
    """Which agent/role issued it. Needed for conflict attribution."""

    opaque: bool = False
    """True for raw code execution and any edit that cannot be replayed deterministically.

    An opaque operation is an **undo barrier**: rolling back across one requires a
    snapshot restore rather than a replay, and everything upstream of it cannot be
    re-evaluated. This is a real hole in the parametric model and it is recorded
    explicitly rather than hidden (ADR-002, ADR-009).
    """

    produced_objects: tuple[str, ...] = ()
    status: OperationStatus = OperationStatus.PENDING


@dataclass(frozen=True, slots=True)
class OperationResult:
    op_id: str
    ok: bool
    produced_objects: tuple[str, ...] = ()
    modified_objects: tuple[str, ...] = ()
    removed_objects: tuple[str, ...] = ()
    error_rule: str = ""
    error_detail: str = ""
    error_suggestion: str = ""


@dataclass(frozen=True, slots=True)
class ActionReport:
    """What an agent gets back after every action.

    Gate A 4.1 chose "what changed + key measurements + new problems" over full scene
    state (which grows without limit — 14k tokens per call at 400 objects) and over bare
    success/failure (which means the agent never learns the railing now clips the tread,
    because in practice it does not think to ask).
    """

    op_id: str
    ok: bool
    summary: str
    changed: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    new_problems: tuple[Defect, ...] = ()
    resolved_problems: tuple[Defect, ...] = ()
    error_rule: str = ""
    error_detail: str = ""
    error_suggestion: str = ""
    checks_scope: str = "changed+neighbours"
    checks_skipped: bool = False
    """True when the configured cadence skipped verification for this call. A report with
    no problems and ``checks_skipped=True`` is not a clean bill of health, and must never
    be presented as one."""

    def render(self) -> str:
        """Compact text form. Deliberately terse: token efficiency has a measured
        cost/accuracy tradeoff and a concise format runs about a third the tokens of a
        verbose one."""
        lines = [f"{'OK' if self.ok else 'FAIL'} {self.op_id} — {self.summary}"]
        if self.changed:
            lines.append(f"CHANGED  {len(self.changed)} object(s): {', '.join(self.changed[:8])}")
        for m in self.measurements:
            lines.append(f"MEASURE  {m.describe()}")
        for d in self.new_problems:
            lines.append(f"PROBLEM  {d.describe()}")
        if self.checks_skipped:
            lines.append("NOTE     verification skipped by cadence setting — not a clean result")
        if not self.ok:
            lines.append(f"ERROR    {self.error_rule}: {self.error_detail}")
            if self.error_suggestion:
                lines.append(f"TRY      {self.error_suggestion}")
        return "\n".join(lines)


class ToolRole(StrEnum):
    """Sub-agent roles. Each sees only its own tools.

    This is not a nicety. The accuracy-optimal number of visible tools measures around
    2-7; past ~30, description overlap makes agents invent tool names and borrow argument
    schemas from the wrong tool. Role-partitioning is what keeps each agent's visible set
    in the range where it can choose correctly (ADR-003).
    """

    BLOCKOUT = "blockout"
    REFINE = "refine"
    DETAIL = "detail"
    POLISH = "polish"
    INSPECT = "inspect"
    """Read-only. Any number of these may run concurrently (ADR-007)."""

    EXPORT = "export"
    ADMIN = "admin"
    """Checkpoints, rollback, raw execution."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One MCP tool, declared beside the operation it exposes.

    Registry *content* lives with the operation; registry *policy* — transports,
    partitioning, image downscaling — lives in ``src/mcp/``. This keeps ``mcp`` a thin
    collector rather than a second place operations get defined.
    """

    name: str
    description: str
    roles: tuple[ToolRole, ...]
    input_schema: dict[str, Any]
    handler: Callable[..., Any] | None = None
    mutating: bool = True
    """Mutating tools require the single write lock. Read-only tools do not, which is
    what lets many inspect agents run beside the one writer."""

    examples: tuple[str, ...] = ()


class ToolError(Exception):
    """The error shape every tool failure takes.

    Gate A 4.2, verbatim: the agent is told *which rule broke*. Never a raw traceback,
    never a bare code — practitioner reports consistently describe agents looping on the
    same failing call when handed opaque errors.
    """

    def __init__(self, rule: str, detail: str, suggestion: str = "") -> None:
        super().__init__(f"{rule}: {detail}" + (f" — {suggestion}" if suggestion else ""))
        self.rule = rule
        self.detail = detail
        self.suggestion = suggestion

    def as_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "detail": self.detail, "suggestion": self.suggestion}
