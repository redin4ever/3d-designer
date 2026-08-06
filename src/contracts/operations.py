"""Operations, joinery intent, and the MCP tool declaration shape.

An *operation* is one typed, parametric, validated unit of work with a re-runnable
acceptance query. Operations are neither primitives (``add_cube`` — a railing takes ~140
of them and drift accumulates over that distance) nor whole-object composites
(``build("a staircase")`` — measured at -12.6% Exec@1 because the model must get a dozen
parameters right at once with no intermediate check). ADR-004.

**Over the 300-line soft cap, deliberately** (Rule 2): every type here is part of one
frozen surface that sixteen modules import, and this package's import order is acyclic by
hand (see ``CLAUDE.md``). Splitting it would add an import edge between two halves of the
same concept and buy nothing — the seam would be "the first half", which the rule names as
a bad seam. It is under a third of the hard cap and stays there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from .constraints import ConstraintSet
from .engine import EngineProtocol
from .errors import RuleError
from .export_profiles import AssetClass
from .measurement import AcceptanceQuery, Defect, Measurement, MeasurementReport

__all__ = [
    "OperationStatus",
    "JoineryIntent",
    "Operation",
    "OperationResult",
    "OperationHandler",
    "HandlerRegistry",
    "Proposal",
    "ActionReport",
    "ExportReport",
    "ToolRole",
    "ToolSpec",
    "MutatingHandler",
    "ReadHandler",
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

    axis: str = ""
    """Which world axis the part is inserted along — ``"x"``, ``"y"``, ``"z"``, or empty.

    A socket depth is a distance along **one** direction. The overlap between two boxes is
    three numbers, and picking the wrong one is not a rounding error: for a post driven
    through a deck, the smallest overlap is the post's own cross-section, which stays tiny
    no matter how far through it goes. Comparing a declared 150 mm socket against that
    reported a post 500 mm clean through the deck as within intent.

    Empty means "use the deepest overlap", which is the right default: a socket is by
    definition an insertion, so the axis it goes in along is the one with the most overlap.
    Name it explicitly when the geometry is ambiguous.
    """

    def permits(self, insertion_depth: float) -> bool:
        """Whether this declared joint covers how far the part is actually inserted.

        ``insertion_depth`` must be the overlap **along the axis the part goes in**, which
        the caller computes (``measure.find_clipping``). It is deliberately not the
        minimum-translation distance: for a post driven through a deck, the smallest
        overlap is the post's own cross-section, which stays tiny however far through it
        goes — and comparing a declared 150 mm socket against that reported a post 500 mm
        clean through as within intent.
        """
        return insertion_depth <= self.depth + self.tolerance

    def axis_index(self) -> int | None:
        return {"x": 0, "y": 1, "z": 2}.get(self.axis.lower())


@dataclass(frozen=True, slots=True)
class Operation:
    """One entry in the scene document's ordered log.

    The log is the source of truth; geometry is generated from it. This is what makes
    undo a pointer move rather than a snapshot restore, and what keeps constraints live.
    """

    op_id: str
    kind: str
    """The operation name, e.g. ``add_railing``. Must resolve in the handler registry;
    validated at append time by the scene document rather than here, because the set of
    registered kinds is owned by the operation modules, not by contracts."""

    params: dict[str, Any] = field(default_factory=dict)
    placements: tuple[ConstraintSet, ...] = ()
    joinery: tuple[JoineryIntent, ...] = ()
    acceptance: tuple[AcceptanceQuery, ...] = ()
    phase: str = "blockout"
    author: str = ""
    """Which agent/role issued it. Needed for conflict attribution."""

    target_objects: tuple[str, ...] = ()
    """Existing objects this operation acts *upon*, as opposed to ``produced_objects``
    which it creates. Conflict detection compares these, so an operation that does not
    declare what it touches cannot be checked against a concurrent one."""

    asset_class: AssetClass | None = None
    """Which polygon budget applies to what this produces. Without it the per-class
    budgets in the export profiles are unreachable and only the platform's hard ceiling
    can ever be checked."""

    proposal_id: str = ""
    """Provenance, when this operation came from a read-only sub-agent's proposal."""

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
    assumptions: tuple[str, ...] = ()
    """Values the handler supplied because the caller omitted them.

    Gate A 6.4 chose that this tool never carries a table of real-world dimensions — the
    agent supplies every one. Phase 6 found ``add_railing`` quietly defaulting three
    cross-sections to 5cm/5cm/3cm, invisibly. Gate B 1.4 kept the defaults and required
    them to be *reported*, which is this field: an agent that can see what was assumed on
    its behalf can correct it, and one that cannot is being handed a hidden dimension
    table under another name.

    One human-readable line per assumption, naming the parameter and the value used.
    """


@runtime_checkable
class OperationHandler(Protocol):
    """How an operation kind is executed and re-executed.

    Five separately-owned modules (``ops``, ``align``, ``gaps``, ``detail``, ``uv``)
    contribute operations, and ``scene`` must replay all of them deterministically. Without
    one declared calling convention here, each module would expose its operations however
    it saw fit and ``scene`` would need five hand-written adapters — or five authors would
    have to converge on an identical convention by luck.

    A handler must be **deterministic**: the same operation against the same engine state
    must produce the same geometry. Replay depends on it (ADR-002).
    """

    def __call__(self, engine: EngineProtocol, op: Operation) -> OperationResult: ...


#: What each operation module exports and ``scene`` composes. Keys are operation kinds.
HandlerRegistry = dict[str, OperationHandler]


@dataclass(frozen=True, slots=True)
class Proposal:
    """A change a read-only sub-agent wants made.

    Inspect-role agents cannot write. They measure, critique, and return one of these; the
    single writer applies it. This is how parallelism is real without concurrent mutation
    (ADR-007). It lives here rather than beside the phase machinery because a proposal is
    structurally an un-applied :class:`Operation`, and it must convert into one without
    losing fields.
    """

    proposal_id: str
    author: str
    target_objects: tuple[str, ...]
    operation_kind: str
    params: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    supporting_defects: tuple[Defect, ...] = ()

    def to_operation(self, op_id: str, phase: str) -> Operation:
        """Convert losslessly. ``target_objects`` and provenance survive; ``rationale``
        and ``supporting_defects`` are argument, not instruction, and are deliberately
        dropped here — they belong in the log line, not in replayable state."""
        return Operation(
            op_id=op_id,
            kind=self.operation_kind,
            params=dict(self.params),
            phase=phase,
            author=self.author,
            target_objects=self.target_objects,
            proposal_id=self.proposal_id,
        )


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

    proposals: tuple[Proposal, ...] = ()
    """What a read-only inspect tool returns instead of changes. Typed here so an inspect
    handler has somewhere real to put a proposal, rather than serialising one into
    ``summary`` text that conflict detection would then have to parse back out."""

    operator_notes: tuple[str, ...] = ()
    """Free-text instructions the human typed while the run was in flight.

    MCP is call/response — a server cannot push into a connected agent's context
    uninvited. So a redirect typed into the browser has exactly one way to reach the
    agent: riding out on the next tool response. This field is that path, and it is
    required rather than optional, because the alternative is smuggling it into
    ``summary`` where two implementations will do it two different ways.
    """

    assumptions: tuple[str, ...] = ()
    """Carried up from :attr:`OperationResult.assumptions` — what the tool supplied that
    the agent did not (Gate B 1.4)."""

    breakdown: tuple[tuple[str, int], ...] = ()
    """``(kind, count)`` pairs summarising what was produced, when the per-object list is
    too long to send.

    Gate B 4.3: one ``add_railing`` returned ~3,398 tokens listing dimensions and triangle
    count for all 40 objects it made, and a small room cost ~5,400 tokens of check output
    alone. Above :data:`DETAIL_THRESHOLD` objects the report carries this plus totals
    instead, and ``detail_hint`` names the tool that will give per-object detail on
    request. Pairs rather than a dict so the report stays comparable and hashable.
    """

    detail_omitted: int = 0
    """How many objects' per-object detail was left out. Never silently zero when
    something was dropped — a summarised report that does not say it summarised reads as
    a complete one, which is the same failure as ``checks_skipped`` and is why that field
    exists too."""

    detail_hint: str = ""
    """How to get what was omitted, e.g. ``"call describe_object(<id>)"``."""

    total_triangles: int = 0

    def render(self) -> str:
        """Compact text form. Deliberately terse: token efficiency has a measured
        cost/accuracy tradeoff and a concise format runs about a third the tokens of a
        verbose one."""
        lines = [f"{'OK' if self.ok else 'FAIL'} {self.op_id} — {self.summary}"]
        if self.changed:
            lines.append(f"CHANGED  {len(self.changed)} object(s): {', '.join(self.changed[:8])}")
        if self.breakdown:
            parts = ", ".join(f"{n}x {kind}" for kind, n in self.breakdown)
            lines.append(f"MADE     {parts}" + (f" — {self.total_triangles} tris" if self.total_triangles else ""))
        for m in self.measurements:
            lines.append(f"MEASURE  {m.describe()}")
        for d in self.new_problems:
            lines.append(f"PROBLEM  {d.describe()}")
        for a in self.assumptions:
            lines.append(f"ASSUMED  {a}")
        if self.detail_omitted:
            lines.append(
                f"NOTE     per-object detail omitted for {self.detail_omitted} object(s)"
                + (f" — {self.detail_hint}" if self.detail_hint else "")
            )
        if self.checks_skipped:
            lines.append("NOTE     verification skipped by cadence setting — not a clean result")
        for note in self.operator_notes:
            lines.append(f"OPERATOR {note}")
        if not self.ok:
            lines.append(f"ERROR    {self.error_rule}: {self.error_detail}")
            if self.error_suggestion:
                lines.append(f"TRY      {self.error_suggestion}")
        return "\n".join(lines)


DETAIL_THRESHOLD = 8
"""Above this many changed objects, an :class:`ActionReport` summarises instead of listing.

Eight is the measured knee, not a round number: at 40 objects the per-object form cost
~3,398 tokens against ~220 summarised, and below about eight the per-object form is both
cheaper than a follow-up call and more useful. Gate B 4.3.
"""


@dataclass(frozen=True, slots=True)
class ExportReport:
    """The outcome of an export.

    Distinct from :class:`ActionReport`, which is shaped around an operation id. Export is
    not an operation on the model — it is a file being written — and the warning banner
    (Gate A 6.3) needs somewhere typed to travel from export through to the browser.
    """

    path: str
    profile: str
    ok: bool
    triangle_count: int = 0
    defects: tuple[Defect, ...] = ()
    budget: int | None = None
    over_budget_by: int = 0
    forced: bool = False
    """True when the user exported past a blocking defect. Recorded, never silent."""

    @property
    def banner(self) -> str:
        if not self.defects and not self.over_budget_by:
            return f"Exported {self.path} for {self.profile} — {self.triangle_count} tris, clean."
        parts = [f"Exported {self.path} for {self.profile} with issues:"]
        for d in self.defects:
            parts.append(f"  - {d.describe()}")
        if self.over_budget_by:
            parts.append(
                f"  - {self.triangle_count} tris is {self.over_budget_by} over the "
                f"{self.budget} budget for this profile"
            )
        return "\n".join(parts)


class ToolRole(StrEnum):
    """Sub-agent roles. Each sees only its own tools.

    This is not a nicety. The accuracy-optimal number of visible tools measures around
    2-7; past ~30, description overlap makes agents invent tool names and borrow argument
    schemas from the wrong tool. Role-partitioning is what keeps each agent's visible set
    in the range where it can choose correctly (ADR-003).
    """

    BLOCKOUT = "blockout"

    REFINE = "refine"
    """Construction that changes what the model *is* — openings, stairs, railings."""

    REPAIR = "repair"
    """Fixing what is broken: holes, welds, normals, shells, visual gaps.

    Split out of ``REFINE`` during integration. Construction, repair and alignment are all
    refine-phase work, so all three modules correctly declared ``REFINE`` — and the
    combined set reached 19 tools, more than double the accuracy-optimal bound. The
    registry's fair-capping fallback then silently hid ``repair``, ``make_plumb`` and
    ``close_visual_gap``, which are core operations. Three roles inside one phase is the
    real fix; capping was the symptom.
    """

    ALIGN = "align"
    """Angle and alignment snaps — parallel, perpendicular, coplanar, plumb, flush, grid."""
    DETAIL = "detail"
    POLISH = "polish"
    INSPECT = "inspect"
    """Read-only. Any number of these may run concurrently (ADR-007)."""

    EXPORT = "export"
    ADMIN = "admin"
    """Checkpoints, rollback, raw execution."""


@runtime_checkable
class MutatingHandler(Protocol):
    """A tool that changes the model. Always returns an :class:`ActionReport`."""

    def __call__(self, **params: Any) -> ActionReport: ...


@runtime_checkable
class ReadHandler(Protocol):
    """A read-only tool. Returns measurements, and may return proposals; never mutates."""

    def __call__(self, **params: Any) -> MeasurementReport | ActionReport: ...


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
    handler: MutatingHandler | ReadHandler | None = None
    """Typed per kind so ``mcp`` can serialise a response without duck-typing its way to
    one. A handler returning the wrong shape is otherwise discovered at runtime, for one
    tool, the first time anybody calls it."""

    mutating: bool = True
    """Mutating tools require the single write lock. Read-only tools do not, which is
    what lets many inspect agents run beside the one writer."""

    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mutating and ToolRole.INSPECT in self.roles:
            raise ValueError(
                f"tool {self.name!r} is mutating but exposed to the INSPECT role. Many "
                "inspect agents run concurrently precisely because none of their tools "
                "can mutate — this combination breaks that guarantee (ADR-007)."
            )
        if not self.roles:
            raise ValueError(f"tool {self.name!r} is visible to no role, so nothing can call it")


class ToolError(RuleError):
    """The error shape every tool failure takes.

    Gate A 4.2, verbatim: the agent is told *which rule broke*. Never a raw traceback,
    never a bare code — practitioner reports consistently describe agents looping on the
    same failing call when handed opaque errors.

    Now a :class:`~contracts.errors.RuleError`, sharing one shape with ``EngineError``,
    ``LockContention``, ``RunPaused`` and ``ProposalConflict``. That is what lets the
    boundary in ``app/handlers.py`` catch *one* type and treat anything else as an unnamed
    failure to be wrapped, which is how Gate A 4.2 becomes total rather than partial.
    """
