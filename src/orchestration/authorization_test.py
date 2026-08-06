"""Tests for ADR-013 — role authority lives on the lease, and is checked against the phase.

Measured live in Phase 6 against the real product: ``dispatch`` checked only the role string
*the caller itself supplied* and never compared it to the session's phase, so a POLISH tool
(``unwrap_uvs``) and a REFINE tool (``add_railing``) both succeeded silently while the
session had never left ``blockout``. Any agent could claim any role by saying so. Every test
here exists because that hole was real, shipped, and invisible to three green suites.
"""

from __future__ import annotations

import pytest

from contracts import ALWAYS_LEGAL_ROLES, Phase, PhaseViolation, ToolRole, roles_for_phase
from orchestration import Orchestrator


def _enter(scene, phase: Phase) -> None:
    """Put the session in ``phase`` without promoting.

    Deliberately reaches into the document rather than calling ``promote()``: ADR-012 made
    promotion a hard gate with no override, and a test helper that could step around it
    would be that override under another name. Phase *entry* is what these tests need;
    whether the gate can be passed is ``phases_test.py``'s subject.
    """
    scene.document.phase = phase


def test_acquire_puts_the_granted_roles_on_the_lease(scene) -> None:
    """If the lease did not carry roles, the only place authority could live is the role
    string the caller sends with each call — which is exactly the hole ADR-013 closes. An
    agent that can name its own role is not partitioned at all; it is unpartitioned with
    extra steps."""
    orch = Orchestrator(scene)

    lease = orch.acquire("writer-a", Phase.BLOCKOUT, roles=(ToolRole.BLOCKOUT,))

    assert lease.roles == (ToolRole.BLOCKOUT,)
    assert ToolRole.BLOCKOUT in lease.granted_roles()


def test_an_empty_role_grant_means_everything_legal_in_the_phase(scene) -> None:
    """The ordinary single-agent session must not have to enumerate roles to do anything.
    If an empty grant meant "no roles", the default call — ``acquire(holder, phase)`` — would
    produce a lease that permits nothing, and every existing caller would break into a
    refusal loop with no error explaining why."""
    orch = Orchestrator(scene)

    lease = orch.acquire("writer-a", Phase.REFINE)

    assert lease.roles == ()
    assert set(lease.granted_roles()) == set(roles_for_phase(Phase.REFINE))


def test_authorize_refuses_a_tool_whose_role_the_lease_does_not_hold(scene) -> None:
    """A narrowed lease that does not actually narrow anything is a coordination mechanism
    that coordinates nothing: two agents partitioned into "build" and "repair" would both
    still be able to run either, and the conflict the partition exists to prevent happens
    anyway."""
    orch = Orchestrator(scene)
    _enter(scene, Phase.REFINE)
    lease = orch.acquire("writer-a", Phase.REFINE, roles=(ToolRole.REPAIR,))

    with pytest.raises(PhaseViolation):
        orch.authorize("add_railing", (ToolRole.REFINE,), lease)


def test_authorize_refuses_a_polish_tool_while_the_session_is_in_blockout(scene) -> None:
    """The exact call the Phase 6 review made and watched succeed. ``unwrap_uvs`` is a
    POLISH tool; a session that has never left ``blockout`` unwrapping UVs means the staged
    plan the user chose at Gate A 3.2 constrains nothing, and geometry gets detailed and
    polished before its shape is settled — the "stitched together" failure this product
    exists to answer."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    assert orch.phase is Phase.BLOCKOUT

    with pytest.raises(PhaseViolation):
        orch.authorize("unwrap_uvs", (ToolRole.POLISH,), lease)


def test_authorize_ignores_the_role_a_caller_claims_and_reads_the_lease(scene) -> None:
    """The whole of ADR-013 in one assertion: passing POLISH as the tool's declared role
    does not grant POLISH. Before this, naming a role *was* holding it, so the refusal below
    could be bypassed by any agent that simply asked for the tool it wanted."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT, roles=(ToolRole.BLOCKOUT,))

    with pytest.raises(PhaseViolation):
        orch.authorize("unwrap_uvs", (ToolRole.POLISH,), lease)

    orch.authorize("add_primitive", (ToolRole.BLOCKOUT,), lease)  # must not raise


def test_authorize_allows_repair_and_align_from_detail_onward(scene) -> None:
    """ADR-012 removed the promotion override, so an operation that leaves a non-manifold
    edge in ``detail`` would otherwise produce a phase that can never pass its own acceptance
    query and can never be left. Fixing what you just broke must not require going
    backwards; if this fails, an unattended run deadlocks with nobody to redirect it."""
    orch = Orchestrator(scene)
    _enter(scene, Phase.DETAIL)
    lease = orch.acquire("writer-a", Phase.DETAIL)

    orch.authorize("split_non_manifold", (ToolRole.REPAIR,), lease)  # must not raise
    orch.authorize("make_plumb", (ToolRole.ALIGN,), lease)  # must not raise


def test_a_refusal_names_the_phase_the_tool_and_what_is_legal_here(scene) -> None:
    """Gate A 4.2: the agent is told which rule broke and what to do instead. A refusal
    saying only "not allowed" makes an agent retry the same call forever — and since ADR-012
    removed the override, an agent that cannot work out how to move forward has no escape at
    all."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)

    with pytest.raises(PhaseViolation) as exc:
        orch.authorize("unwrap_uvs", (ToolRole.POLISH,), lease)

    message = str(exc.value)
    assert "unwrap_uvs" in message
    assert "blockout" in message
    assert "polish" in message
    assert exc.value.tool == "unwrap_uvs"
    assert exc.value.phase is Phase.BLOCKOUT
    assert exc.value.required == (ToolRole.POLISH,)
    assert "promote" in exc.value.suggestion


def test_an_inspect_tool_needs_no_lease_at_all(scene) -> None:
    """Read-only access must never require the write lock, or the "many readers, one
    writer" guarantee ADR-007 rests on collapses into "one agent at a time" — every inspect
    agent would queue behind the writer for the whole run."""
    orch = Orchestrator(scene)
    orch.acquire("writer-a", Phase.BLOCKOUT)  # somebody else holds the write lock

    orch.authorize("measure_dimensions", (ToolRole.INSPECT,), None)  # must not raise


def test_a_mutating_tool_with_no_lease_is_refused(scene) -> None:
    """The mirror of the test above. If a lease-less caller could reach a mutating tool
    because ``authorize`` shrugged at ``lease=None``, the write lock would be advisory for
    exactly the callers most likely to skip acquiring one."""
    orch = Orchestrator(scene)

    with pytest.raises(PhaseViolation):
        orch.authorize("add_primitive", (ToolRole.BLOCKOUT,), None)


def test_same_holder_reacquire_narrows_the_granted_roles(scene) -> None:
    """An agent that finishes building and switches to inspecting should not have to wait
    out its own lease to drop privileges it no longer needs. If re-acquiring could not
    narrow, the safest thing an agent could do — voluntarily giving up write roles — would
    be the thing that costs it the lock."""
    orch = Orchestrator(scene)
    orch.acquire("writer-a", Phase.REFINE, roles=(ToolRole.REFINE, ToolRole.REPAIR))

    narrowed = orch.acquire("writer-a", Phase.REFINE, roles=(ToolRole.REPAIR,))

    assert narrowed.holder == "writer-a"
    assert narrowed.roles == (ToolRole.REPAIR,)
    assert orch.current().roles == (ToolRole.REPAIR,)


def test_same_holder_reacquire_widens_the_granted_roles(scene) -> None:
    """The other direction: an agent that discovers mid-phase that it also needs to align
    something must be able to widen without releasing, because releasing is the one moment
    another agent can take the lock away and leave the run half-built."""
    orch = Orchestrator(scene)
    _enter(scene, Phase.REFINE)
    orch.acquire("writer-a", Phase.REFINE, roles=(ToolRole.REPAIR,))

    widened = orch.acquire("writer-a", Phase.REFINE, roles=(ToolRole.REPAIR, ToolRole.ALIGN))

    assert set(widened.roles) == {ToolRole.REPAIR, ToolRole.ALIGN}
    orch.authorize("make_plumb", (ToolRole.ALIGN,), widened)  # must not raise


def test_admin_and_inspect_stay_legal_in_every_phase(scene) -> None:
    """``ADMIN`` owns checkpoints, rollback and raw execution — exactly the tools an agent
    reaches for when it has got itself stuck. Locking those behind a phase would wedge the
    run at the precise moment the escape hatch is needed."""
    orch = Orchestrator(scene)

    for phase in (Phase.BLOCKOUT, Phase.REFINE, Phase.DETAIL, Phase.POLISH):
        _enter(scene, phase)
        lease = orch.acquire("writer-a", phase)
        for role in ALWAYS_LEGAL_ROLES:
            orch.authorize("raw_execute", (role,), lease)  # must not raise
