"""Tests for proposals and conflict flagging — the read side of "many readers, one
writer" (ADR-007, Gate A 10.3).

Two guarantees, each load-bearing: ``propose`` must work with no write lease at all, or
every read-only INSPECT agent would be blocked for a writer's entire turn, defeating the
entire point of allowing many of them to run at once; and a conflict must never be
resolved silently, because last-writer-wins is specifically wrong for geometry (moving a
wall while another proposal attaches a railing to it produces an invalid model, not just
a surprise). Most tests here fail with ``NotImplementedError`` until ``proposals.py`` is
implemented (Rule 4), which is expected for this phase.
"""

from __future__ import annotations

import pytest

from contracts import Phase, Proposal
from orchestration import Orchestrator, ProposalConflict


def test_propose_needs_no_lease_even_while_a_writer_holds_one(scene) -> None:
    """``propose``'s signature carries no ``WriteLease`` parameter at all — there is no
    way to even pass one, which is the strongest form of this guarantee: no
    implementation choice could start requiring a lease without also breaking the call
    shape every INSPECT-role caller uses. This test proves the *behaviour* matches: five
    concurrent proposals succeed, and go on succeeding, while a single writer holds the
    lock the entire time — the whole mechanism that makes parallelism real without
    concurrent mutation."""
    orch = Orchestrator(scene)
    orch.acquire("writer-a", Phase.BLOCKOUT)  # the lock is held for the whole test

    ids = [
        orch.propose(
            Proposal(
                proposal_id=f"p{i}", author=f"inspect-{i}",
                target_objects=(f"wall_{i}",), operation_kind="align_face",
            )
        )
        for i in range(5)
    ]

    assert ids == [f"p{i}" for i in range(5)]
    assert len(orch.pending()) == 5
    assert orch.current().holder == "writer-a", "propose must not disturb the write lock"


def test_two_proposals_with_overlapping_targets_produce_a_named_conflict(scene) -> None:
    """A conflict that does not name both authors and the shared geometry is not
    actionable — an operator or a resolving agent has to know *who* touched *what*
    before either proposal can be resubmitted or dropped (Gate A 10.3's "surfaced with
    the exact geometry involved, like a merge conflict")."""
    orch = Orchestrator(scene)
    p1 = Proposal(
        proposal_id="p1", author="inspect-1", target_objects=("wall_3",),
        operation_kind="align_face",
    )
    p2 = Proposal(
        proposal_id="p2", author="inspect-2", target_objects=("wall_3", "post_1"),
        operation_kind="attach_railing",
    )
    orch.propose(p1)
    orch.propose(p2)

    conflicts = orch.find_conflicts()

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert {p.author for p in conflict.proposals} == {"inspect-1", "inspect-2"}
    assert "wall_3" in conflict.overlapping_objects


def test_two_proposals_on_disjoint_objects_produce_no_conflicts(scene) -> None:
    """The mirror image of the test above: flagging a conflict between proposals that
    never actually touch the same geometry would make every parallel read-only pass
    grind to a false halt, defeating ADR-007's entire premise that disjoint work should
    proceed without coordination."""
    orch = Orchestrator(scene)
    orch.propose(
        Proposal(
            proposal_id="p1", author="inspect-1", target_objects=("wall_1",),
            operation_kind="align_face",
        )
    )
    orch.propose(
        Proposal(
            proposal_id="p2", author="inspect-2", target_objects=("wall_2",),
            operation_kind="align_face",
        )
    )

    assert orch.find_conflicts() == ()


def test_accept_refuses_a_conflicted_proposal_rather_than_picking_a_winner(scene) -> None:
    """ADR-007 explicitly rejected Figma-style last-writer-wins for geometry: a post
    socketed into a deck and a wall silently moved out from under it are not "a
    surprise", they are an invalid model. If ``accept`` applied one side of a known
    conflict anyway, this exact failure mode would ship, silently, on every run that
    happens to have two proposals touching the same object."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.propose(
        Proposal(
            proposal_id="p1", author="inspect-1", target_objects=("wall_3",),
            operation_kind="align_face",
        )
    )
    orch.propose(
        Proposal(
            proposal_id="p2", author="inspect-2", target_objects=("wall_3",),
            operation_kind="move_wall",
        )
    )
    assert orch.find_conflicts() != ()

    with pytest.raises(ProposalConflict):
        orch.accept("p1", lease)

    assert scene.document.head == 0, "a conflicted proposal must never be silently applied"
