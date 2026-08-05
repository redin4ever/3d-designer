"""Tests for ``history.py``: ``undo``, ``redo``, ``rollback_to``, ``checkpoint``
(ADR-006).

Every test works through the public ``Scene`` interface only. The whole point of ADR-006
is that undo/redo/rollback are pointer moves plus a replay — observable solely through the
geometry and ``ChangeKind`` that result, never through any special-cased internal state.
"""

from __future__ import annotations

import pytest

from contracts import ChangeKind
from scene import Scene


def test_undo_removes_the_last_operations_object_and_moves_head_back(
    engine, handlers, add_cube_op
):
    """If undo does not actually reach into the engine, the operator sees the head
    counter move back while the object it 'undid' is still sitting in the viewport — the
    log and the geometry disagreeing is exactly what ADR-002 exists to prevent."""
    scene = Scene(engine, handlers)
    for i, name in enumerate(("a", "b", "c")):
        scene.apply(add_cube_op(f"op{i}", name))

    kind = scene.undo(1)

    assert kind == ChangeKind.ROLLBACK
    assert not engine.exists("c")
    assert engine.exists("b") and engine.exists("a")
    assert scene.document.head == 2


def test_redo_restores_the_undone_operations_object_identically(engine, handlers, add_cube_op):
    """Redo must reproduce the exact geometry the original apply produced, not merely an
    object with the same name — otherwise redo is silently lossy."""
    scene = Scene(engine, handlers)
    for i, name in enumerate(("a", "b", "c")):
        scene.apply(add_cube_op(f"op{i}", name, size=2.0))
    before = engine.snapshot("c")
    scene.undo(1)

    kind = scene.redo(1)

    assert kind == ChangeKind.ROLLBACK
    assert engine.exists("c")
    after = engine.snapshot("c")
    assert after.vertices == before.vertices
    assert after.triangles == before.triangles
    assert scene.document.head == 3


def test_undo_past_the_beginning_raises(engine, handlers, add_cube_op):
    """Chosen policy, documented in README's 'Undo/redo' section: undo past the start of
    the log raises rather than clamping to 0. A silent clamp would make 'undo 5' and
    'undo 1' indistinguishable to the caller whenever fewer than 5 operations exist."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.undo(1)

    with pytest.raises(ValueError):
        scene.undo(1)


def test_apply_after_undo_truncates_the_undone_op_for_good(engine, handlers, add_cube_op):
    """SceneDocument.append truncates anything previously undone (contracts_test.py::
    test_appending_after_an_undo_truncates_the_undone_tail); this is the same guarantee
    observed through scene.apply, proving scene actually goes through append rather than
    mutating document.operations directly."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.apply(add_cube_op("op2", "b"))
    scene.apply(add_cube_op("op3", "c"))
    scene.undo(1)  # c undone, head == 2

    scene.apply(add_cube_op("op4", "d"))  # a different op — must drop op3 for good

    assert [o.op_id for o in scene.document.operations] == ["op1", "op2", "op4"]
    assert not engine.exists("c")
    assert engine.exists("d")
    with pytest.raises(ValueError):
        scene.redo(1)  # nothing left to redo to; op3 does not come back
    assert not engine.exists("c")


def test_opaque_operation_creates_a_recorded_barrier(engine, handlers, add_cube_op, tmp_path):
    """An opaque op with no recorded barrier lets a later rollback attempt a replay
    across code that cannot be replayed, producing wrong geometry with no error — the
    exact failure ADR-006 names barriers as the fix for."""
    scene = Scene(engine, handlers)
    snapshot_file = tmp_path / "snap.blend"
    snapshot_file.write_text("not a real blend file, just a path that exists")

    scene.apply(add_cube_op("op1", "a", opaque=True), snapshot_path=str(snapshot_file))

    assert len(scene.document.barriers) == 1
    assert scene.document.barriers[0].op_id == "op1"
    assert scene.document.barriers[0].snapshot_path == str(snapshot_file)


def test_undo_not_crossing_a_barrier_returns_rollback(engine, handlers, add_cube_op, tmp_path):
    scene = Scene(engine, handlers)
    snapshot_file = tmp_path / "snap.blend"
    snapshot_file.write_text("x")
    scene.apply(add_cube_op("op1", "a", opaque=True), snapshot_path=str(snapshot_file))
    scene.apply(add_cube_op("op2", "b"))

    kind = scene.undo(1)  # undoes only "b"; the barrier at op1 stays active

    assert kind == ChangeKind.ROLLBACK


def test_undo_across_a_barrier_returns_full_resync(engine, handlers, add_cube_op, tmp_path):
    """Replaying is never valid across an opaque edit. This is what tells a caller to
    stop and do a full resync (a snapshot restore) instead of trusting an incremental
    diff that would silently reconstruct the wrong geometry with no error at all."""
    scene = Scene(engine, handlers)
    snapshot_file = tmp_path / "snap.blend"
    snapshot_file.write_text("x")
    scene.apply(add_cube_op("op1", "a", opaque=True), snapshot_path=str(snapshot_file))
    scene.apply(add_cube_op("op2", "b"))
    scene.undo(1)  # b only — ROLLBACK, barrier untouched

    kind = scene.undo(1)  # now undoes the opaque op1 itself

    assert kind == ChangeKind.FULL_RESYNC


def test_rollback_to_a_checkpoint_restores_exactly_that_state(engine, handlers, add_cube_op):
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.apply(add_cube_op("op2", "b"))
    cp = scene.checkpoint("two-cubes")
    snap_a, snap_b = engine.snapshot("a"), engine.snapshot("b")
    scene.apply(add_cube_op("op3", "c"))
    scene.apply(add_cube_op("op4", "d"))

    kind = scene.rollback_to("two-cubes")

    assert kind == ChangeKind.ROLLBACK
    assert scene.document.head == cp.index == 2
    assert set(engine.list_objects()) == {"a", "b"}
    assert engine.snapshot("a").vertices == snap_a.vertices
    assert engine.snapshot("b").vertices == snap_b.vertices


def test_checkpoint_emits_a_checkpoint_change_event(engine, handlers, add_cube_op):
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    events = []
    scene.subscribe(events.append)

    scene.checkpoint("cp1")

    assert len(events) == 1
    assert events[0].kind == ChangeKind.CHECKPOINT
