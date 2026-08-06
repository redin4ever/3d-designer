"""Move, rotate, scale, delete, duplicate, rename and set-material (Q-14).

Seven operations that did not exist. Before this, all 33 replayable kinds were construction
or repair, so there was no way to nudge a thing four centimetres left — the smallest possible
correction cost a whole round trip through the model.

They are ordinary logged operations, not direct engine writes, and that is Q-19's answer:
one shared history. Replay, checkpoints and roll-back-N-steps come for free, and it becomes
impossible for two timelines to describe one scene.
"""

from __future__ import annotations

import pytest

from contracts import ToolError, Transform, Vec3
from ops import OPS
from testing import FakeEngine


@pytest.fixture()
def engine() -> FakeEngine:
    e = FakeEngine()
    e.create_primitive("box", "cube", Vec3(1, 1, 1), Transform())
    return e


def _op(kind: str, **params):
    from contracts import Operation

    return Operation(op_id=f"op-{kind}", kind=kind, params=params)


def _run(engine, kind, **params):
    return OPS[kind](engine, _op(kind, **params))


# ─── move ───────────────────────────────────────────────────────────────────────────


def test_moving_a_part_puts_it_where_you_asked(engine) -> None:
    """The smallest useful correction in the product, and the one there was no way to make
    without spending a whole model turn on it."""
    result = _run(engine, "move_object", object_id="box", translation=[2.0, 0.0, 1.0], snap=0)

    assert result.ok
    assert result.modified_objects == ("box",)
    t = engine.snapshot("box").transform.translation
    assert (round(t.x, 4), round(t.y, 4), round(t.z, 4)) == (2.0, 0.0, 1.0)


def test_moving_snaps_to_the_grid_by_default(engine) -> None:
    """Q-16 chose grid snap on by default. Every placement being a fraction off is precisely
    the defect class this product measures, and free-hand dragging produces exactly that."""
    _run(engine, "move_object", object_id="box", translation=[1.03, 2.07, 0.01])

    t = engine.snapshot("box").transform.translation
    assert (round(t.x, 4), round(t.y, 4), round(t.z, 4)) == (1.0, 2.1, 0.0)


def test_snapping_can_be_turned_off(engine) -> None:
    """The other half of Q-16. Some placements are deliberately off-grid, and a snap that
    cannot be disabled turns a helpful default into something to fight."""
    _run(engine, "move_object", object_id="box", translation=[1.03, 0.0, 0.0], snap=0)

    assert round(engine.snapshot("box").transform.translation.x, 4) == 1.03


def test_moving_something_that_does_not_exist_says_so_by_name(engine) -> None:
    """An operator can drag a part the agent deleted a moment ago. A refusal naming the id
    is the difference between "that is gone" and a stack trace."""
    with pytest.raises(ToolError, match="no_such"):
        _run(engine, "move_object", object_id="no_such", translation=[0, 0, 0])


def test_a_move_with_a_malformed_position_is_refused_before_it_reaches_the_engine(engine) -> None:
    """Entry validation is this package's standing contract: an out-of-shape parameter that
    reaches the engine surfaces as an opaque failure three calls later."""
    with pytest.raises(ToolError):
        _run(engine, "move_object", object_id="box", translation=[1.0, 2.0])


# ─── rotate ─────────────────────────────────────────────────────────────────────────


def test_rotating_turns_the_part_about_the_axis_you_named(engine) -> None:
    """Axis-and-degrees rather than a quaternion because that is what a drag handle
    produces, and because snapping an angle is expressible in degrees and not in a
    quaternion's four components."""
    result = _run(engine, "rotate_object", object_id="box", axis="z", degrees=90, snap_degrees=0)

    assert result.ok
    assert engine.snapshot("box").transform.rotation != Transform().rotation


def test_rotation_snaps_to_fifteen_degrees_by_default(engine) -> None:
    """The angular counterpart of grid snap. A railing at 89.6 degrees looks right and
    measures wrong, which is the whole failure mode this product exists to catch."""
    _run(engine, "rotate_object", object_id="box", axis="z", degrees=88)

    # 88 snaps to 90; the resulting quaternion is the 90-degree one about z.
    rotation = engine.snapshot("box").transform.rotation
    assert round(rotation.w, 4) == round(2 ** -0.5, 4)


def test_an_unknown_axis_is_refused_rather_than_silently_doing_nothing(engine) -> None:
    """A typo that produced no rotation and no error would read as "rotation is broken"."""
    with pytest.raises(ToolError, match="axis"):
        _run(engine, "rotate_object", object_id="box", axis="w", degrees=90)


# ─── scale ──────────────────────────────────────────────────────────────────────────


def test_scaling_resizes_the_part(engine) -> None:
    result = _run(engine, "scale_object", object_id="box", scale=[2.0, 2.0, 2.0])

    assert result.ok
    assert round(engine.snapshot("box").transform.scale.x, 4) == 2.0


def test_scaling_to_zero_is_refused(engine) -> None:
    """A zero scale collapses the mesh to a plane and every measurement taken from it
    afterwards is meaningless — a degenerate state this library refuses on entry
    everywhere else too (F-013, Gate B 5.4)."""
    with pytest.raises(ToolError, match="scale"):
        _run(engine, "scale_object", object_id="box", scale=[1.0, 0.0, 1.0])


# ─── delete and duplicate ───────────────────────────────────────────────────────────


def test_deleting_removes_the_part_and_reports_it_as_removed(engine) -> None:
    """``removed_objects`` is what tells the viewer to drop the node and the agent that the
    id is gone. A delete that reported nothing would leave a ghost in both."""
    result = _run(engine, "delete_object", object_id="box")

    assert result.ok
    assert result.removed_objects == ("box",)
    assert not engine.exists("box")


def test_duplicating_produces_a_second_part_and_leaves_the_first_alone(engine) -> None:
    result = _run(engine, "duplicate_object", object_id="box", new_id="box_copy")

    assert result.ok
    assert engine.exists("box")
    assert result.produced_objects and engine.exists(result.produced_objects[0])


def test_a_duplicate_can_be_offset_so_it_is_not_hidden_inside_the_original(engine) -> None:
    """Duplicating in place puts two identical objects at the same coordinates, which looks
    exactly like nothing happening and is the first thing anyone tries."""
    result = _run(engine, "duplicate_object", object_id="box", new_id="box_copy", offset=[1, 0, 0])

    copy_id = result.produced_objects[0]
    assert round(engine.snapshot(copy_id).transform.translation.x, 4) == 1.0


# ─── rename and material ────────────────────────────────────────────────────────────


def test_renaming_keeps_the_geometry_and_frees_the_old_name(engine) -> None:
    """Q-14 asked for a name you will recognise. ``EngineProtocol`` has no rename, so this
    is duplicate-then-delete — which is why the test asserts the geometry survived rather
    than only that the ids changed."""
    before = engine.snapshot("box").triangle_count

    result = _run(engine, "rename_object", object_id="box", new_id="crate")

    assert result.ok
    assert not engine.exists("box")
    renamed = result.produced_objects[0]
    assert engine.snapshot(renamed).triangle_count == before


def test_renaming_onto_a_name_that_is_taken_is_refused(engine) -> None:
    """The engine auto-uniquifies on collision (``FakeEngine._unique``), so without this
    guard a rename to a taken name silently produces a third name and the operator's part
    is called something neither of them chose."""
    engine.create_primitive("crate", "cube", Vec3(1, 1, 1), Transform())

    with pytest.raises(ToolError, match="crate"):
        _run(engine, "rename_object", object_id="box", new_id="crate")


def test_assigning_a_material_reports_the_object_as_modified(engine) -> None:
    material = engine.create_material("paint", (0.5, 0.5, 0.5))

    result = _run(engine, "set_object_material", object_id="box", material_id=material)

    assert result.ok
    assert result.modified_objects == ("box",)


# ─── the registry ───────────────────────────────────────────────────────────────────


def test_every_new_operation_is_replayable(engine) -> None:
    """``OPS`` is what ``scene`` replays every logged operation through. An operation missing
    from it applies once and then vanishes on the next replay or rollback — and Q-19 chose
    one shared history, which makes replay the thing everything else rests on."""
    for kind in (
        "move_object",
        "rotate_object",
        "scale_object",
        "delete_object",
        "duplicate_object",
        "rename_object",
        "set_object_material",
    ):
        assert kind in OPS, f"{kind} cannot be replayed"


def test_every_new_operation_is_declared_as_a_tool() -> None:
    """A handler with no spec is unreachable by any agent, with no error anywhere — and the
    operator's own edits are meant to be things the agent can also do and can also see."""
    from ops import OP_SPECS

    declared = {spec.name for spec in OP_SPECS}
    for kind in (
        "move_object",
        "rotate_object",
        "scale_object",
        "delete_object",
        "duplicate_object",
        "rename_object",
        "set_object_material",
    ):
        assert kind in declared, f"{kind} is not declared as a tool"
