"""Read-many, write-one: proposals and conflict flagging (ADR-007, Gate A 10.3).

INSPECT-role agents cannot write; they call ``propose`` — a method whose signature
carries no ``WriteLease`` parameter at all, so there is no implementation choice that
could start requiring one without also breaking every caller's call shape. That is the
entire mechanism that makes many concurrent readers real without concurrent mutation.

``find_conflicts`` never resolves anything automatically: last-writer-wins is
specifically wrong for geometry (moving a wall while another proposal attaches a railing
to it produces an invalid model, not just a surprise — ADR-007's "Consequences"). A
conflicted proposal can only be accepted after the conflict is gone — never overridden by
``accept`` itself.

Nothing here computes anything yet — every method raises until an implementer replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import ActionReport, Conflict, Proposal, WriteLease

_NOT_IMPLEMENTED = "orchestration.{name}: not implemented"


class ProposalConflict(RuntimeError):
    """Raised by ``accept`` when the named proposal is party to an unresolved conflict.

    Shaped like every other named error in this codebase — ``rule``, ``detail``,
    ``suggestion`` (see ``contracts.EngineError``, ``contracts.ConstraintError``,
    ``contracts.ToolError``) — rather than a bare string, per Gate A 4.2: an agent told
    which proposals conflict and over which objects can resolve it; one given a generic
    exception cannot.

    Not defined in ``src/contracts/`` because Rule 5 reserves that package for the main
    agent; this is orchestration's own addition pending reconciliation (see this task's
    ``contractRequests`` output).
    """

    def __init__(self, rule: str, detail: str, suggestion: str = "") -> None:
        super().__init__(f"{rule}: {detail}" + (f" — {suggestion}" if suggestion else ""))
        self.rule = rule
        self.detail = detail
        self.suggestion = suggestion


class ProposalsMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def propose(self, p: Proposal) -> str:
        """Queue ``p`` and return its ``proposal_id``.

        Deliberately takes no ``WriteLease`` and must never call ``self.verify`` — this
        is what lets any number of INSPECT-role agents call it while a writer holds the
        lock (ADR-007). Once implemented, appends to an internal pending list keyed by
        ``proposal_id``; a duplicate id is a caller bug and should raise rather than
        silently overwrite (the same reasoning as
        ``contracts.SceneDocument.append``'s duplicate ``op_id`` check — ids key state
        that a duplicate would silently clobber).
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="propose"))

    def pending(self) -> tuple[Proposal, ...]:
        """Every proposal not yet accepted or dropped, in submission order."""
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="pending"))

    def find_conflicts(self) -> tuple[Conflict, ...]:
        """Pair up pending proposals whose ``target_objects`` overlap and return one
        :class:`contracts.Conflict` per overlapping pair (or group), naming every author
        and every shared object — never silently picking a winner (Gate A 10.3). Two
        proposals on disjoint ``target_objects`` produce nothing.

        ``Conflict.__post_init__`` already refuses to construct one with fewer than two
        proposals or with no overlapping objects, so an implementation that tries to
        build one for a lone proposal, or with no genuinely shared object, fails loudly
        at construction rather than shipping a phantom conflict.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="find_conflicts"))

    def accept(self, proposal_id: str, lease: WriteLease) -> ActionReport:
        """Apply the named proposal as an operation and return the standard report.

        The write lock (``self.verify(lease)``) is required here exactly as it is for
        any other mutation — accepting a proposal is the one moment it stops being a
        read. Expected to convert the proposal via ``Proposal.to_operation`` and route
        through the same path ``reporting.perform`` uses, so cadence and operator notes
        are decided in exactly one place.

        Must raise :class:`ProposalConflict` — never silently choose a winner — when
        ``proposal_id`` is a party to any conflict in ``self.find_conflicts()``. Gate A
        10.3 and ADR-007 are explicit that last-writer-wins is wrong for geometry; the
        caller must resolve the conflict (drop one side, or submit a merged proposal)
        before either proposal can be accepted.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="accept"))
