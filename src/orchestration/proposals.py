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

Every method here can be called from any number of threads at once — that is what INSPECT
agents *are* — so the pending list is guarded and read through one snapshot per call. See
``find_conflicts`` for the ``KeyError`` that came out of getting this wrong.
"""

from __future__ import annotations

from contracts import ActionReport, Conflict, Proposal, WriteLease

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
        lock (ADR-007). Appends to an internal pending list keyed by ``proposal_id``; a
        duplicate id is a caller bug and raises rather than silently overwriting (the same reasoning as
        ``contracts.SceneDocument.append``'s duplicate ``op_id`` check — ids key state
        that a duplicate would silently clobber).
        """
        with self._pending_mutex:
            if any(existing.proposal_id == p.proposal_id for existing in self._pending):
                raise ValueError(
                    f"proposal id {p.proposal_id!r} is already pending; ids key state a "
                    "duplicate would silently clobber"
                )
            self._pending.append(p)
        return p.proposal_id

    def pending(self) -> tuple[Proposal, ...]:
        """Every proposal not yet accepted or dropped, in submission order."""
        with self._pending_mutex:
            return tuple(self._pending)

    def find_conflicts(self) -> tuple[Conflict, ...]:
        """Pair up pending proposals whose ``target_objects`` overlap and return one
        :class:`contracts.Conflict` per overlapping pair (or group), naming every author
        and every shared object — never silently picking a winner (Gate A 10.3). Two
        proposals on disjoint ``target_objects`` produce nothing.

        ``Conflict.__post_init__`` already refuses to construct one with fewer than two
        proposals or with no overlapping objects, so an implementation that tries to
        build one for a lone proposal, or with no genuinely shared object, fails loudly
        at construction rather than shipping a phantom conflict.

        Works from **one snapshot** of the pending list, taken under the lock. Every INSPECT
        agent in the run calls ``propose`` concurrently by design (ADR-007), and re-reading
        ``self._pending`` between the union-find build and the grouping pass meant an id that
        arrived in between reached ``find()`` with no entry in ``parent`` — a bare
        ``KeyError`` out of a read-only method, which is a reader being refused for doing
        exactly what the design invites it to do. ``concurrency_test.py`` raised 168 of them
        in one run.
        """
        pending = self.pending()
        parent: dict[str, str] = {p.proposal_id: p.proposal_id for p in pending}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        owners_by_object: dict[str, list[str]] = {}
        for p in pending:
            for obj in p.target_objects:
                owners_by_object.setdefault(obj, []).append(p.proposal_id)

        for owners in owners_by_object.values():
            for other in owners[1:]:
                union(owners[0], other)

        groups: dict[str, list[Proposal]] = {}
        for p in pending:
            groups.setdefault(find(p.proposal_id), []).append(p)

        conflicts: list[Conflict] = []
        for group in groups.values():
            if len(group) < 2:
                continue
            group_ids = {p.proposal_id for p in group}
            overlapping = tuple(
                sorted(
                    obj
                    for obj, owners in owners_by_object.items()
                    if len(set(owners) & group_ids) >= 2
                )
            )
            if not overlapping:
                continue
            conflicts.append(
                Conflict(
                    conflict_id="conflict-" + "-".join(sorted(group_ids)),
                    proposals=tuple(group),
                    overlapping_objects=overlapping,
                    detail=(
                        f"{len(group)} pending proposals from "
                        f"{', '.join(sorted({p.author for p in group}))} touch "
                        f"{', '.join(overlapping)}"
                    ),
                )
            )
        return tuple(conflicts)

    def accept(self, proposal_id: str, lease: WriteLease) -> ActionReport:
        """Apply the named proposal as an operation and return the standard report.

        The write lock (``self.verify(lease)``) is required here exactly as it is for
        any other mutation — accepting a proposal is the one moment it stops being a
        read. Converts the proposal via ``Proposal.to_operation`` and routes through the
        same ``reporting.perform`` path as everything else, so cadence and operator notes
        are decided in exactly one place.

        Must raise :class:`ProposalConflict` — never silently choose a winner — when
        ``proposal_id`` is a party to any conflict in ``self.find_conflicts()``. Gate A
        10.3 and ADR-007 are explicit that last-writer-wins is wrong for geometry; the
        caller must resolve the conflict (drop one side, or submit a merged proposal)
        before either proposal can be accepted.
        """
        proposal = next((p for p in self.pending() if p.proposal_id == proposal_id), None)
        if proposal is None:
            raise KeyError(f"no pending proposal named {proposal_id!r}")

        for conflict in self.find_conflicts():
            if any(p.proposal_id == proposal_id for p in conflict.proposals):
                raise ProposalConflict(
                    rule="orchestration.proposal_conflict",
                    detail=conflict.describe(),
                    suggestion=(
                        "resolve the conflict (drop one side or submit a merged "
                        "proposal) before accepting either"
                    ),
                )

        op = proposal.to_operation(op_id=proposal_id, phase=self.phase.value)
        report = self.perform(op, lease)
        with self._pending_mutex:
            self._pending = [p for p in self._pending if p.proposal_id != proposal_id]
        return report
