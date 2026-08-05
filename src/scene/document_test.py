"""Tests for ``document.py``: ``apply``, ``replay``, the write lock, and the failure
contract.

``apply``/``replay`` are the two functions everything else in this package is built on —
history, cache invalidation and events all happen inside or around a call to one of them.
If either lies about what happened to the log or the engine, every other test in this
package inherits the lie.
"""

from __future__ import annotations

import pytest

from contracts import LockContention, Operation, Phase, WriteLease
from scene import Scene
from testing import FakeEngine


# --------------------------------------------------------------------- determinism

def test_two_fresh_scenes_given_the_same_ops_produce_identical_geometry(
    engine, handlers, add_cube_op
):
    """The load-bearing property named in the module brief: if two scenes built from the
    same log disagree on geometry, replay cannot be trusted, and undo — implemented as
    replay from a moved pointer — is not actually a pointer move."""
    engine_b = FakeEngine()
    scene_a = Scene(engine, handlers)
    scene_b = Scene(engine_b, handlers)

    ops = [add_cube_op(f"op{i}", name, size=float(i) + 1) for i, name in enumerate(("a", "b", "c"))]
    for op in ops:
        scene_a.apply(op)
        scene_b.apply(op)

    for name in ("a", "b", "c"):
        snap_a, snap_b = engine.snapshot(name), engine_b.snapshot(name)
        assert snap_a.vertices == snap_b.vertices
        assert snap_a.triangles == snap_b.triangles


def test_replay_reproduces_identical_geometry(engine, handlers, add_cube_op):
    """If replay() is not deterministic, undo is not a pointer move and nothing else in
    this module is true (module brief, verbatim). A replay that fails to reset the engine
    first would also fail this test outright: FakeEngine renames a colliding object id
    rather than overwriting it, so the object would silently disappear under its expected
    name."""
    scene = Scene(engine, handlers)
    for i, name in enumerate(("a", "b", "c")):
        scene.apply(add_cube_op(f"op{i}", name, size=float(i) + 1))
    before = {name: engine.snapshot(name) for name in ("a", "b", "c")}

    scene.replay()

    after = {name: engine.snapshot(name) for name in ("a", "b", "c")}
    for name in ("a", "b", "c"):
        assert after[name].vertices == before[name].vertices
        assert after[name].triangles == before[name].triangles


# ------------------------------------------------------------------- basic apply

def test_apply_of_a_delete_op_removes_the_object_and_advances_the_log(
    engine, handlers, add_cube_op, delete_op
):
    """Exercises the second fake handler end to end — apply() must not special-case
    'creates something' as the only shape a successful operation can take; a handler
    reporting removed_objects has to flow through append/cache-invalidate/emit exactly
    like one reporting produced_objects."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))

    result = scene.apply(delete_op("op2", "a"))

    assert result.ok is True
    assert not engine.exists("a")
    assert scene.document.head == 2


# ---------------------------------------------------------------------- write lock

def test_apply_with_no_lock_held_and_no_lease_succeeds(engine, handlers, add_cube_op):
    """Single-agent decision, documented in README's 'Write lock' section: with nobody
    holding the write lock, apply() does not demand a lease. If this ever regressed to
    requiring one unconditionally, every solo run without an orchestration module
    acquiring one would be unable to make a single edit."""
    scene = Scene(engine, handlers)

    result = scene.apply(add_cube_op("op1", "a"))

    assert result.ok is True
    assert engine.exists("a")


def test_apply_with_a_mismatched_lease_raises_lock_contention(engine, handlers, add_cube_op):
    """A caller holding the wrong lease must never mutate a scene someone else currently
    owns — ADR-007's single-writer guarantee. Losing this lets two agents corrupt each
    other's work exactly as ADR-007 exists to prevent."""
    scene = Scene(engine, handlers)
    scene.document.active_lease = WriteLease(
        holder="writer-a", phase=Phase.BLOCKOUT, lease_id="L1", granted_at_op=0, expires_at_op=64,
    )
    forged = WriteLease(
        holder="writer-b", phase=Phase.BLOCKOUT, lease_id="L2", granted_at_op=0, expires_at_op=64,
    )

    with pytest.raises(LockContention):
        scene.apply(add_cube_op("op1", "a"), lease=forged)
    assert not engine.exists("a")


def test_apply_with_the_correct_lease_succeeds(engine, handlers, add_cube_op):
    scene = Scene(engine, handlers)
    lease = WriteLease(
        holder="writer-a", phase=Phase.BLOCKOUT, lease_id="L1", granted_at_op=0, expires_at_op=64,
    )
    scene.document.active_lease = lease

    result = scene.apply(add_cube_op("op1", "a"), lease=lease)

    assert result.ok is True
    assert engine.exists("a")


def test_apply_with_no_lease_while_a_lock_is_held_raises(engine, handlers, add_cube_op):
    """A caller supplying no proof at all must be treated the same as a wrong one while
    the lock is genuinely held — 'I didn't bring a lease' is not an exemption."""
    scene = Scene(engine, handlers)
    scene.document.active_lease = WriteLease(
        holder="writer-a", phase=Phase.BLOCKOUT, lease_id="L1", granted_at_op=0, expires_at_op=64,
    )

    with pytest.raises(LockContention):
        scene.apply(add_cube_op("op1", "a"))
    assert not engine.exists("a")


# ------------------------------------------------------------------------- failure

def test_a_raising_handler_leaves_the_log_and_engine_untouched(engine, handlers):
    """A failed operation must not be half-recorded: if the log advanced past a handler
    that raised, undo/redo bookkeeping and the object list would disagree about what
    actually exists, and every later operation would replay against a log entry whose
    handler never actually succeeded."""
    scene = Scene(engine, handlers)
    events = []
    scene.subscribe(events.append)

    with pytest.raises(RuntimeError, match="handler exploded"):
        scene.apply(Operation(op_id="op1", kind="boom"))

    assert scene.document.head == 0
    assert scene.document.active_operations == []
    assert engine.list_objects() == []
    assert events == [], "nothing changed, so no listener should have been notified"


def test_apply_with_an_unregistered_kind_raises_before_touching_the_engine(engine, handlers):
    scene = Scene(engine, handlers)

    with pytest.raises(KeyError, match="unknown_kind"):
        scene.apply(Operation(op_id="op1", kind="unknown_kind"))

    assert scene.document.head == 0
    assert engine.calls == []


def test_apply_of_an_opaque_op_without_a_snapshot_path_fails_before_touching_the_engine(
    engine, handlers, add_cube_op
):
    """contracts.SceneDocument.append already refuses an opaque operation with no
    snapshot_path (contracts_test.py::
    test_opaque_operation_requires_a_snapshot_and_creates_a_barrier); apply() must
    enforce this before calling the handler, not after, or a raw edit would already have
    run against the engine by the time the missing snapshot is discovered."""
    scene = Scene(engine, handlers)
    op = add_cube_op("op1", "a", opaque=True)

    with pytest.raises(ValueError, match="snapshot"):
        scene.apply(op)

    assert engine.calls == []
    assert scene.document.head == 0
