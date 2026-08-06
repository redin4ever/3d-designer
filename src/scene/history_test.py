"""Tests for ``history.py``: ``undo``, ``redo``, ``rollback_to``, ``checkpoint``
(ADR-006).

Every test works through the public ``Scene`` interface only. The whole point of ADR-006
is that undo/redo/rollback are pointer moves plus a replay — observable solely through the
geometry and ``ChangeKind`` that result, never through any special-cased internal state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts import ChangeKind, Vec3
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


# ------------------------------------------------ surviving a log it cannot fully replay

def test_a_scene_mixing_pre_existing_and_logged_geometry_survives_a_whole_history_cycle(
    engine, handlers, add_cube_op, move_op
):
    """F-010, both halves together, in the shape the live failure took. Opening an
    existing `.blend` (`build_app(reset_scene=False)`) means the log legitimately contains
    operations against geometry no logged operation produced. Before this, the first
    `undo` raised `EngineError` from inside `replay()` and `redo`, `rollback_to` and every
    later `undo` failed identically for the rest of the session — the operator's only
    remaining option was to restart and lose the run."""
    engine.create_primitive("existing_wall", "cube", Vec3(1.0, 1.0, 1.0))
    scene = Scene(engine, handlers)
    scene.apply(move_op("op1", "existing_wall"))
    scene.apply(add_cube_op("op2", "a"))
    scene.checkpoint("after-a")
    scene.apply(add_cube_op("op3", "b"))
    scene.apply(add_cube_op("op4", "c"))

    assert scene.undo(2) == ChangeKind.ROLLBACK
    assert scene.redo(1) == ChangeKind.ROLLBACK
    assert scene.rollback_to("after-a") == ChangeKind.ROLLBACK
    assert scene.undo(1) == ChangeKind.ROLLBACK

    assert scene.document.head == 1
    assert engine.exists("existing_wall") is False, (
        "the pre-existing wall cannot be rebuilt from a log that never made it — the "
        "scene must say so rather than pretend"
    )
    assert not engine.exists("a")


def test_an_unreplayable_operation_is_reported_on_the_event_the_undo_emits(
    engine, handlers, add_cube_op, move_op
):
    """Gate B 5.2 — 'reject where we can, survive where we can't'. Surviving silently is
    not surviving: the live view would show a scene missing an operation the operator
    still believes is applied. The skip has to reach whoever asked for the undo."""
    engine.create_primitive("existing_wall", "cube", Vec3(1.0, 1.0, 1.0))
    scene = Scene(engine, handlers)
    scene.apply(move_op("op1", "existing_wall"))
    scene.apply(add_cube_op("op2", "a"))
    scene.apply(add_cube_op("op3", "b"))
    events = []
    scene.subscribe(events.append)

    scene.undo(1)

    assert len(events) == 1
    assert "op1" in events[0].log_line
    assert [s.op_id for s in scene.last_replay.skipped] == ["op1"]


# ------------------------------------------------------- barriers restore, never re-run

def test_undo_across_a_raw_barrier_restores_geometry_instead_of_re_running_the_script(
    engine, handlers, add_cube_op, random_object_op
):
    """F-011. A non-deterministic `raw_execute` made `randobj_f9dd53`; undoing past it and
    redoing forward produced three differently-named objects while the system reported a
    clean `FULL_RESYNC`. Every rebuild went through `replay()`, which re-executes the
    script — the captured snapshot was never read back. Arbitrary code must be restored
    from, never re-run, or undo quietly rewrites the scene it claimed to restore."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    op = random_object_op("op2")
    scene.apply(op, snapshot_path=scene.capture_snapshot("op2"))
    scene.apply(add_cube_op("op3", "c"))
    before = set(engine.list_objects())

    assert scene.undo(2) == ChangeKind.FULL_RESYNC
    assert set(engine.list_objects()) == {"a"}, "the barrier's own object survived an undo past it"

    assert scene.redo(2) == ChangeKind.FULL_RESYNC

    assert set(engine.list_objects()) == before, (
        "redo re-ran the opaque script instead of restoring it — the scene came back with "
        "differently-named geometry"
    )


def test_an_undo_stopping_short_of_a_barrier_still_never_re_runs_the_script(
    engine, handlers, add_cube_op, random_object_op
):
    """The deepest form of the same defect: *any* rebuild started from `engine.reset()`
    and re-ran every logged operation, so even an undo that reported a plain `ROLLBACK`
    silently replaced the raw script's output. Nothing may re-execute an opaque operation,
    whatever ChangeKind the move reports."""
    scene = Scene(engine, handlers)
    op = random_object_op("op1")
    scene.apply(op, snapshot_path=scene.capture_snapshot("op1"))
    produced = [o for o in engine.list_objects() if o.startswith("randobj_")]
    scene.apply(add_cube_op("op2", "b"))

    assert scene.undo(1) == ChangeKind.ROLLBACK

    assert [o for o in engine.list_objects() if o.startswith("randobj_")] == produced
    assert not engine.exists("b")


def test_rollback_to_a_checkpoint_across_a_barrier_restores_rather_than_re_runs(
    engine, handlers, add_cube_op, random_object_op
):
    """`rollback_to` is the operator-facing control Gate A 5.4 asked for by name — pause,
    roll back, redirect. It shares undo's rebuild path and must share its guarantee, or
    the one control a human reaches for under pressure is the one that silently changes
    the scene."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.checkpoint("before-raw")
    scene.apply(random_object_op("op2"), snapshot_path=scene.capture_snapshot("op2"))
    scene.apply(add_cube_op("op3", "c"))

    assert scene.rollback_to("before-raw") == ChangeKind.FULL_RESYNC

    assert set(engine.list_objects()) == {"a"}


def test_capture_snapshot_records_geometry_not_the_operation_log(
    engine, handlers, add_cube_op
):
    """The capture half shipped in QA round 2 called `scene.save()`, which serialises the
    *operation log* — and an opaque operation is by definition one the log does not
    describe, so restoring from it restored nothing at all. A barrier's snapshot has to be
    geometry or the barrier is decorative."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a", size=3.0))

    path = scene.capture_snapshot("op-next")
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    assert "operations" not in data, "this is the operation log again, not geometry"
    assert [o["object_id"] for o in data["objects"]] == ["a"]
    assert data["objects"][0]["vertices"], "an object recorded with no vertices restores nothing"
