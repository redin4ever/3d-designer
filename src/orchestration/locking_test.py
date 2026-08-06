"""Tests for the single write lock — the safety property everything else rests on
(ADR-007).

A live 3D scene is shared mutable state, structurally the case where parallel LLM writers
are measured to corrupt each other's work. The write lock is the entire mechanism that
prevents it: exactly one lease may be live at a time, a lease not currently live must be
rejected, and a lease from a dead agent must expire so it cannot wedge the run forever.
Every test here is written against that contract, not against how the lock happens to be
stored internally — most will fail with ``NotImplementedError`` until ``locking.py`` is
implemented (Rule 4: tests come first), which is expected and correct for this phase.
"""

from __future__ import annotations

import pytest

from contracts import LockContention, Operation, Phase, WriteLease, WriteLockManager
from orchestration import Orchestrator


def test_second_acquire_by_a_different_holder_names_the_first_holder(scene) -> None:
    """If a second writer could acquire while the first is still live, two agents could
    both believe they hold the only write lock and mutate the scene concurrently — the
    exact failure ADR-007 exists to rule out. Naming the current holder (rather than a
    bare ``RuntimeError``) is what lets the second agent wait usefully instead of retrying
    immediately, forever."""
    orch = Orchestrator(scene)
    orch.acquire("writer-a", Phase.BLOCKOUT)

    with pytest.raises(LockContention) as exc:
        orch.acquire("writer-b", Phase.BLOCKOUT)

    assert exc.value.holder == "writer-a"


def test_release_then_a_different_holder_can_acquire(scene) -> None:
    """A lock that cannot be handed off after a legitimate release would force every
    phase to have exactly one writer for its entire duration, with no way to swap in a
    fresh agent between operations."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)

    orch.release(lease)
    new_lease = orch.acquire("writer-b", Phase.BLOCKOUT)

    assert new_lease.holder == "writer-b"
    assert orch.current().holder == "writer-b"


def test_verify_raises_for_a_lease_that_is_not_the_current_one(scene) -> None:
    """``verify`` runs before every mutation. If it accepted a forged or stale lease
    value an agent built or kept around itself, the write lock would be advisory rather
    than enforced — ``contracts.WriteLease``'s own docstring: two agents each holding a
    lease they constructed themselves is not a lock, it is two agents with the same
    dataclass."""
    orch = Orchestrator(scene)
    orch.acquire("writer-a", Phase.BLOCKOUT)
    forged = WriteLease(
        holder="writer-b", phase=Phase.BLOCKOUT, lease_id="not-live",
        granted_at_op=0, expires_at_op=64,
    )

    with pytest.raises(LockContention):
        orch.verify(forged)


def test_verify_passes_for_the_current_lease(scene) -> None:
    """The mirror image of the test above: if ``verify`` also rejected the genuinely
    live lease, no mutation could ever proceed and the write path would be dead for
    every legitimate caller, not just forged ones."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)

    orch.verify(lease)  # must not raise


def test_a_stale_lease_is_reclaimable_by_a_different_holder(scene) -> None:
    """Agents die mid-operation (Rule 6). Without expiry, a dead agent's lease wedges the
    run forever — nobody else can ever acquire, and the whole multi-agent build stalls
    with no path forward. This is the one property an implementation with no expiry
    logic at all would fail."""
    orch = Orchestrator(scene)
    orch.acquire("writer-a", Phase.BLOCKOUT, ttl_ops=2)

    # advance the run's clock — operation count, not wall-clock time — past the lease's
    # expiry, standing in for writer-a going silent mid-run.
    scene.apply(Operation(op_id="op-0", kind="noop"))
    scene.apply(Operation(op_id="op-1", kind="noop"))

    new_lease = orch.acquire("writer-b", Phase.BLOCKOUT)

    assert new_lease.holder == "writer-b"


def test_perform_without_a_valid_lease_raises_and_changes_nothing(scene) -> None:
    """A caller that never held the lock reaching ``self._scene.apply`` anyway would
    make the write lock purely cosmetic — any agent could mutate the scene by simply not
    bothering to acquire first. ``scene.document`` staying untouched is the proof that
    ``perform`` refused before doing any work, not after."""
    orch = Orchestrator(scene)
    op = Operation(op_id="op1", kind="add_cube", target_objects=("box",))
    forged = WriteLease(
        holder="ghost", phase=Phase.BLOCKOUT, lease_id="never-granted",
        granted_at_op=0, expires_at_op=64,
    )

    with pytest.raises(LockContention):
        orch.perform(op, forged)

    assert scene.document.head == 0
    assert scene.document.active_lease is None


def test_orchestrator_structurally_satisfies_write_lock_manager(scene) -> None:
    """``contracts.WriteLockManager`` is declared, not just described, precisely so other
    modules — ``mcp`` gating a mutating call, ``raw`` before an opaque execution,
    ``viewer`` showing lock status — can check for it structurally
    (``@runtime_checkable``). This passes even before the four methods are implemented,
    because a Protocol's ``isinstance`` check only asks whether the methods exist, not
    whether they work yet — it is a shape guarantee, not a behaviour one. A renamed or
    dropped method here would silently break every module that identifies the write lock
    this way, and this is the one test that would catch it immediately."""
    orch = Orchestrator(scene)

    assert isinstance(orch, WriteLockManager)
