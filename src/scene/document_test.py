"""Tests for ``document.py``: ``apply``, ``replay``, the write lock, and the failure
contract.

``apply``/``replay`` are the two functions everything else in this package is built on —
history, cache invalidation and events all happen inside or around a call to one of them.
If either lies about what happened to the log or the engine, every other test in this
package inherits the lie.
"""

from __future__ import annotations

import pytest

from contracts import (
    LockContention,
    Operation,
    Phase,
    RuleError,
    ScenePort,
    Vec3,
    WriteLease,
)
from scene import UNKNOWN_TARGET_RULE, Scene
from testing import FakeEngine


# ------------------------------------------------------------------- the port itself

def test_the_real_scene_satisfies_the_declared_scene_port(engine, handlers):
    """`ScenePort` was wrong twice while living in `orchestration`, each time producing a
    P0 that three green suites could not see — because every double matched the
    *declaration* and nothing ever checked the declaration against the real `Scene`.
    Now that the Protocol is in the frozen surface, this is the check that was missing:
    the thing consumers are handed is the thing they were promised."""
    scene = Scene(engine, handlers)

    assert isinstance(scene, ScenePort)
    for member in ("engine", "document", "apply", "undo", "capture_snapshot", "subscribe"):
        assert hasattr(scene, member), f"Scene is missing ScenePort's {member!r}"


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


# ----------------------------------------------------- targets that cannot be replayed

def test_apply_refuses_an_operation_targeting_an_object_nothing_produced(
    engine, handlers, move_op
):
    """F-010, reject-early half. An operation whose target was never produced by a logged
    operation and was not in the scene when it was constructed poisons the log: replay
    starts from `engine.reset()`, so that target will not exist next time and every later
    undo/redo/rollback in the session raises. Refusing it here turns a crash three
    operations later into an error naming the actual mistake, at the moment it is made."""
    scene = Scene(engine, handlers)

    with pytest.raises(RuleError) as caught:
        scene.apply(move_op("op1", "bad_hole"))

    assert caught.value.rule == UNKNOWN_TARGET_RULE
    assert "bad_hole" in caught.value.detail
    assert scene.document.head == 0, "a refused operation must never reach the log"
    assert engine.calls == [], "refusal must happen before the handler touches the engine"


def test_an_object_present_when_the_scene_was_constructed_is_a_legitimate_target(
    engine, handlers, move_op
):
    """`build_app(reset_scene=False)` — 'open an existing .blend and work on it' — is
    documented and supported. Geometry that was already there is exactly what such a
    session edits, so rejecting it would refuse the entire supported workflow rather than
    the mistake the rule is aimed at."""
    engine.create_primitive("existing_wall", "cube", Vec3(1.0, 1.0, 1.0))
    scene = Scene(engine, handlers)

    result = scene.apply(move_op("op1", "existing_wall"))

    assert result.ok is True
    assert scene.document.head == 1


def test_an_object_an_earlier_operation_produced_is_a_legitimate_target(
    engine, handlers, add_cube_op, move_op
):
    """The other half of the same rule: what the log itself made is always replayable, so
    it must never be refused. A rule strict enough to reject this would block ordinary
    build-then-adjust work, which is most of what the product does."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))

    result = scene.apply(move_op("op2", "a"))

    assert result.ok is True
    assert scene.document.head == 2


def test_replay_skips_an_operation_it_cannot_re_run_and_carries_on(
    engine, handlers, add_cube_op, move_op
):
    """F-010, survive-anyway half. `replay()` rebuilds from `engine.reset()`, so an
    operation against pre-existing geometry cannot run a second time. Aborting the whole
    replay there is what made undo session-fatal: one such operation and every later
    history call raised for the rest of the session. Skipping it and continuing means the
    rest of the scene still comes back."""
    engine.create_primitive("existing_wall", "cube", Vec3(1.0, 1.0, 1.0))
    scene = Scene(engine, handlers)
    scene.apply(move_op("op1", "existing_wall"))
    scene.apply(add_cube_op("op2", "a"))
    scene.apply(add_cube_op("op3", "b"))

    report = scene.replay()

    assert engine.exists("a") and engine.exists("b"), "replay abandoned the rest of the log"
    assert report.complete is False
    assert [s.op_id for s in report.skipped] == ["op1"]


def test_a_replay_report_names_the_operation_it_skipped_and_why(
    engine, handlers, add_cube_op, delete_op
):
    """A replay that silently dropped operations is worse than one that failed — the
    operator sees a scene that looks whole and is missing work nobody mentioned. The
    report has to carry the operation id, its kind and the reason, because that is the
    only thing an agent or a human can act on."""
    engine.create_primitive("existing_wall", "cube", Vec3(1.0, 1.0, 1.0))
    scene = Scene(engine, handlers)
    scene.apply(delete_op("op1", "existing_wall"))
    scene.apply(add_cube_op("op2", "a"))

    report = scene.replay()

    assert report.applied == 1
    assert len(report.skipped) == 1
    skipped = report.skipped[0]
    assert skipped.op_id == "op1"
    assert skipped.kind == "delete_object"
    assert "existing_wall" in skipped.reason
    assert "op1" in report.describe()


def test_a_replay_that_could_not_re_run_something_does_not_break_the_next_one(
    engine, handlers, add_cube_op, move_op
):
    """The reported failure was not one bad call, it was a dead session: after the first
    `EngineError` out of `replay()`, `redo`, `rollback_to` and a second `undo` all failed
    identically and never recovered. Replay must be re-enterable however many operations
    it had to skip."""
    engine.create_primitive("existing_wall", "cube", Vec3(1.0, 1.0, 1.0))
    scene = Scene(engine, handlers)
    scene.apply(move_op("op1", "existing_wall"))
    scene.apply(add_cube_op("op2", "a"))

    first = scene.replay()
    second = scene.replay()

    assert [s.op_id for s in first.skipped] == [s.op_id for s in second.skipped] == ["op1"]
    assert engine.exists("a")


def test_an_unregistered_kind_in_the_log_is_skipped_rather_than_raised_during_replay(
    engine, handlers, add_cube_op
):
    """A scene saved by a build with one more operation module than this one has must
    still open. Raising `KeyError` from inside replay makes the whole document
    unopenable because of a single entry — the file is not corrupt, one operation is
    simply unavailable, and those are very different outcomes."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.document.operations.append(Operation(op_id="op2", kind="from_the_future"))
    scene.document.head = 2

    report = scene.replay()

    assert [s.op_id for s in report.skipped] == ["op2"]
    assert "from_the_future" in report.skipped[0].reason
    assert engine.exists("a")
