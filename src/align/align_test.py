"""Tests for ``align`` — the one-shot geometric snaps.

Written against the contract in ``src/contracts/`` and the maths already proven out in
``src/constraints/`` (this package's IMMEDIATE-SNAP counterpart) before any implementation
existed here (Rule 4) — this file is the spec. Every test is built to fail against at
least one plausible wrong implementation, not just against "no implementation at all":
misaligned starting angles rather than already-aligned ones (an identity-returning stub
would pass a naive already-parallel check), both halves of an axis-scoped move asserted
(a "teleport to the target's position" stub passes a same-axis-only check), and idempotence
checked by re-running rather than assumed.

``ALIGN_SPECS`` is real, constructed data from module import (mirrors
``ops/registry_test.py`` / ``constraints.anchors.AnchorResolution``) — its tests pass from
the start; every other test here fails on ``NotImplementedError`` until the next pass
implements the seven functions and ``measure_angle``.
"""

from __future__ import annotations

import math

import pytest

from contracts import EPSILON, Quat, ToolError, ToolRole, Transform, Vec3, WORLD_UP
from align import (
    ALIGN_SPECS,
    AlignResult,
    make_coplanar,
    make_flush,
    make_parallel,
    make_perpendicular,
    make_plumb,
    measure_angle,
    set_angle,
    snap_to_grid,
)


def _rotated_beam(engine, object_id: str, degrees_about_z: float, *, translation: Vec3 | None = None) -> Vec3:
    """A beam elongated along local +Y, rotated about world Z. Returns the resulting
    world-space direction of its own long axis — mirrors
    ``constraints/solver_kinds_test.py``'s identical helper, so a 50/37-degree starting
    angle here means the same thing it does there."""
    rotation = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(degrees_about_z))
    engine.create_primitive(
        object_id, "cube", Vec3(0.1, 2.0, 0.1),
        Transform(rotation=rotation, translation=translation or Vec3()),
    )
    return rotation.rotate(Vec3(0, 1, 0)).normalized()


# --------------------------------------------------------------------- measure_angle


def test_measure_angle_of_perpendicular_beams_is_ninety(engine) -> None:
    _rotated_beam(engine, "a", 0.0)
    _rotated_beam(engine, "b", 90.0)
    assert measure_angle(engine, "a", "b") == pytest.approx(90.0, abs=1e-3)


def test_measure_angle_never_mutates(engine) -> None:
    _rotated_beam(engine, "a", 0.0)
    _rotated_beam(engine, "b", 37.0)
    before = engine.snapshot("b").transform
    measure_angle(engine, "a", "b")
    assert engine.snapshot("b").transform == before


# --------------------------------------------------------------------- make_parallel


def test_make_parallel_zeroes_the_angle_and_reports_the_starting_misalignment(engine) -> None:
    """Deliberately misaligned by 37 degrees, not already parallel — an implementation
    that just returns the object unchanged would fail this immediately, where an
    already-parallel starting pose would let it slip through."""
    target_dir = _rotated_beam(engine, "target", 0.0)
    _rotated_beam(engine, "mover", 37.0)

    result = make_parallel(engine, "mover", "target")

    assert result.angle_before_deg == pytest.approx(37.0, abs=1e-2)
    assert result.angle_after_deg == pytest.approx(0.0, abs=1e-2)
    assert result.changed is True
    assert measure_angle(engine, "mover", "target") == pytest.approx(0.0, abs=1e-2)
    mover_dir = engine.snapshot("mover").transform.rotation.rotate(Vec3(0, 1, 0)).normalized()
    assert mover_dir.as_tuple() == pytest.approx(target_dir.as_tuple(), abs=1e-3)


def test_make_parallel_can_target_an_explicit_local_axis(engine) -> None:
    """``axis`` must actually be read, not silently ignored in favour of the default."""
    engine.create_primitive("target", "cube", Vec3(2.0, 0.1, 0.1))  # long along local X
    engine.create_primitive(
        "mover", "cube", Vec3(2.0, 0.1, 0.1),
        Transform(rotation=Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(20))),
    )

    make_parallel(engine, "mover", "target", axis="x")

    mover_x = engine.snapshot("mover").transform.rotation.rotate(Vec3(1, 0, 0)).normalized()
    assert mover_x.as_tuple() == pytest.approx((1.0, 0.0, 0.0), abs=1e-3)


# ----------------------------------------------------------------- make_perpendicular


def test_make_perpendicular_lands_on_ninety_not_zero_or_180(engine) -> None:
    """A non-trivial 50-degree start: a stub returning the object's unrotated heading
    (cos 50 degrees is nowhere near 0) fails this the same way it fails in
    ``constraints/solver_kinds_test.py``'s identical setup."""
    _rotated_beam(engine, "target", 0.0)
    _rotated_beam(engine, "mover", 50.0)

    result = make_perpendicular(engine, "mover", "target")

    assert result.angle_after_deg == pytest.approx(90.0, abs=1e-2)
    angle = measure_angle(engine, "mover", "target")
    assert angle == pytest.approx(90.0, abs=1e-2)
    assert angle != pytest.approx(0.0, abs=5.0)
    assert angle != pytest.approx(180.0, abs=5.0)


# ------------------------------------------------------------------------ set_angle


def test_set_angle_produces_exactly_the_requested_degrees(engine) -> None:
    _rotated_beam(engine, "target", 0.0)
    _rotated_beam(engine, "mover", 5.0)

    result = set_angle(engine, "mover", "target", degrees=30.0)

    assert result.angle_after_deg == pytest.approx(30.0, abs=1e-2)
    assert measure_angle(engine, "mover", "target") == pytest.approx(30.0, abs=1e-2)


def test_set_angle_zero_is_equivalent_to_make_parallel(engine) -> None:
    _rotated_beam(engine, "target", 0.0)
    _rotated_beam(engine, "mover_a", 42.0)
    _rotated_beam(engine, "mover_b", 42.0)

    parallel_result = make_parallel(engine, "mover_a", "target")
    angle_result = set_angle(engine, "mover_b", "target", degrees=0.0)

    assert angle_result.angle_after_deg == pytest.approx(parallel_result.angle_after_deg, abs=1e-2)
    assert measure_angle(engine, "mover_b", "target") == pytest.approx(0.0, abs=1e-2)


# ------------------------------------------------------------------------ make_plumb


def test_make_plumb_restores_local_z_to_world_up(engine) -> None:
    """The same correction a railing post needs: local +Z back to world +Z, regardless of
    which way it was tilted."""
    tilt = Quat.from_axis_angle(Vec3(1, 0, 0), math.radians(40))
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 1.0), Transform(rotation=tilt))

    result = make_plumb(engine, "post")

    up_after = engine.snapshot("post").transform.rotation.rotate(Vec3(0, 0, 1)).normalized()
    assert up_after.as_tuple() == pytest.approx(WORLD_UP.as_tuple(), abs=1e-4)
    assert result.angle_before_deg == pytest.approx(40.0, abs=1e-2)
    assert result.angle_after_deg == pytest.approx(0.0, abs=1e-3)
    assert result.changed is True


# --------------------------------------------------------------------- make_coplanar


def test_make_coplanar_puts_every_point_of_the_object_in_the_targets_plane(engine) -> None:
    """Verified by plane-distance over every one of the object's own points, not by
    trusting the rotation — the wall is tilted 15 degrees so a rotation-skipping
    implementation fails immediately (mirrors
    ``constraints/solver_kinds_test.py::test_coplanar_with_puts_every_point_of_the_object_in_the_targets_plane``)."""
    tilt = Quat.from_axis_angle(Vec3(1, 0, 0), math.radians(15))
    engine.create_primitive("wall", "plane", Vec3(4.0, 3.0, 0.0), Transform(rotation=tilt))
    engine.create_primitive("panel", "plane", Vec3(0.6, 0.4, 0.0), Transform(translation=Vec3(9, 9, 9)))
    panel_local_vertices = list(engine.snapshot("panel").vertices)
    wall_point = Vec3(0, 0, 0)
    wall_normal = tilt.rotate(Vec3(0, 0, 1))

    result = make_coplanar(engine, "panel", "wall")

    new_transform = engine.snapshot("panel").transform
    for v in panel_local_vertices:
        world_v = new_transform.apply(v)
        signed_distance = (world_v - wall_point).dot(wall_normal)
        assert signed_distance == pytest.approx(0.0, abs=1e-3)
    assert result.angle_before_deg == pytest.approx(15.0, abs=1e-2)
    assert result.angle_after_deg == pytest.approx(0.0, abs=1e-2)


def test_make_coplanar_face_index_picks_a_real_and_distinct_face(engine) -> None:
    """``face`` must actually change which of the target's planar faces is used — a stub
    that ignores it and always resolves the same default face fails this."""
    engine.create_primitive("target", "cube", Vec3(2.0, 2.0, 2.0))
    original_panel = Transform(translation=Vec3(9, 9, 9))
    engine.create_primitive("panel", "plane", Vec3(0.4, 0.4, 0.0), original_panel)
    panel_local_vertices = list(engine.snapshot("panel").vertices)

    make_coplanar(engine, "panel", "target", face=0)
    t0 = engine.snapshot("panel").transform
    normal0 = t0.rotation.rotate(Vec3(0, 0, 1)).normalized()
    for v in panel_local_vertices:
        assert (t0.apply(v) - t0.translation).dot(normal0) == pytest.approx(0.0, abs=1e-3)

    engine.set_transform("panel", original_panel)
    make_coplanar(engine, "panel", "target", face=3)
    t3 = engine.snapshot("panel").transform
    normal3 = t3.rotation.rotate(Vec3(0, 0, 1)).normalized()

    assert abs(normal0.dot(normal3)) < 0.5, "face=0 and face=3 must resolve to different faces"
    # Every point of a unit-2 cube's face plane sits exactly 1.0m from the origin.
    assert abs(t0.translation.dot(normal0)) == pytest.approx(1.0, abs=1e-3)
    assert abs(t3.translation.dot(normal3)) == pytest.approx(1.0, abs=1e-3)


# ----------------------------------------------------------------------- make_flush


def test_make_flush_removes_the_gap_on_one_axis_and_leaves_the_other_two_untouched(engine) -> None:
    """Both halves asserted: the named axis closes the gap, and the other two position
    axes plus rotation stay exactly where they started — a "move it to the target's
    position" implementation passes the first half and fails the second."""
    engine.create_primitive("wall_b", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(0, 2.0, 3.0)))
    engine.create_primitive("wall_a", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(5.0, 7.0, 9.0)))
    wall_b_face_x = engine.world_bounds("wall_b").maximum.x
    original = engine.snapshot("wall_a").transform

    result = make_flush(engine, "wall_a", "wall_b", axis="x")

    after = engine.snapshot("wall_a").transform
    wall_a_face_x = after.translation.x - 0.1  # half wall_a's own thickness
    assert wall_a_face_x == pytest.approx(wall_b_face_x, abs=EPSILON)
    assert after.translation.y == pytest.approx(original.translation.y, abs=EPSILON), "y must stay untouched"
    assert after.translation.z == pytest.approx(original.translation.z, abs=EPSILON), "z must stay untouched"
    assert after.translation.y != pytest.approx(2.0, abs=0.5), "must not have snapped to the target's own y"
    assert after.translation.z != pytest.approx(3.0, abs=0.5), "must not have snapped to the target's own z"
    assert after.rotation == original.rotation
    assert result.changed is True


# --------------------------------------------------------------------- snap_to_grid


def test_snap_to_grid_puts_bounds_on_grid_multiples(engine) -> None:
    engine.create_primitive("crate", "cube", Vec3(1.0, 1.0, 1.0), Transform(translation=Vec3(1.23, 4.56, 0.11)))

    result = snap_to_grid(engine, "crate", grid=0.5)

    mn = engine.world_bounds("crate").minimum
    for value in (mn.x, mn.y, mn.z):
        remainder = value % 0.5
        assert min(remainder, 0.5 - remainder) < 1e-4
    assert result.changed is True


def test_snap_to_grid_rotation_snaps_to_the_nearest_right_angle(engine) -> None:
    rot37 = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(37))
    engine.create_primitive("a", "cube", Vec3(1, 1, 1), Transform(rotation=rot37))
    rot100 = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(100))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(rotation=rot100))

    snap_to_grid(engine, "a", grid=1.0, rotation_step_deg=90.0)
    snap_to_grid(engine, "b", grid=1.0, rotation_step_deg=90.0)

    dir_a = engine.snapshot("a").transform.rotation.rotate(Vec3(1, 0, 0)).normalized()
    dir_b = engine.snapshot("b").transform.rotation.rotate(Vec3(1, 0, 0)).normalized()
    assert dir_a.as_tuple() == pytest.approx((1.0, 0.0, 0.0), abs=1e-3), "37 degrees rounds down to 0"
    assert dir_b.as_tuple() == pytest.approx((0.0, 1.0, 0.0), abs=1e-3), "100 degrees rounds to 90"


def test_snap_to_grid_with_no_rotation_step_leaves_rotation_untouched(engine) -> None:
    rot = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(13))
    engine.create_primitive("crate", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(1.23, 0, 0), rotation=rot))

    snap_to_grid(engine, "crate", grid=0.5)

    assert engine.snapshot("crate").transform.rotation == rot


# --------------------------------------------------------------------- idempotence


def test_running_any_align_twice_reports_no_change_the_second_time(engine) -> None:
    """An implementation that keeps nudging on every call would compound error across
    hundreds of agent operations — this is the test that would catch it."""
    _rotated_beam(engine, "target", 0.0)
    _rotated_beam(engine, "p_mover", 37.0)
    assert make_parallel(engine, "p_mover", "target").changed is True
    assert make_parallel(engine, "p_mover", "target").changed is False

    _rotated_beam(engine, "q_mover", 50.0)
    assert make_perpendicular(engine, "q_mover", "target").changed is True
    assert make_perpendicular(engine, "q_mover", "target").changed is False

    tilt = Quat.from_axis_angle(Vec3(1, 0, 0), math.radians(40))
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 1.0), Transform(rotation=tilt))
    assert make_plumb(engine, "post").changed is True
    assert make_plumb(engine, "post").changed is False

    engine.create_primitive("wall_b2", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(0, 0, 0)))
    engine.create_primitive("wall_a2", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(5.0, 0, 0)))
    assert make_flush(engine, "wall_a2", "wall_b2", axis="x").changed is True
    assert make_flush(engine, "wall_a2", "wall_b2", axis="x").changed is False

    engine.create_primitive("grid_obj", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(1.23, 0, 0)))
    assert snap_to_grid(engine, "grid_obj", grid=0.5).changed is True
    assert snap_to_grid(engine, "grid_obj", grid=0.5).changed is False

    _rotated_beam(engine, "s_mover", 5.0)
    assert set_angle(engine, "s_mover", "target", degrees=30.0).changed is True
    assert set_angle(engine, "s_mover", "target", degrees=30.0).changed is False


# ----------------------------------------------------------- already aligned, no move


def test_already_aligned_object_reports_no_change_and_does_not_move(engine) -> None:
    _rotated_beam(engine, "target", 0.0)
    _rotated_beam(engine, "mover", 0.0)
    original = engine.snapshot("mover").transform

    result = make_parallel(engine, "mover", "target")

    assert result.changed is False
    assert engine.snapshot("mover").transform == original


def test_already_plumb_object_reports_no_change_and_does_not_move(engine) -> None:
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 1.0))
    original = engine.snapshot("post").transform

    result = make_plumb(engine, "post")

    assert result.changed is False
    assert engine.snapshot("post").transform == original


# ------------------------------------------------------------------- error handling


def test_aligning_to_a_nonexistent_object_raises_a_named_error_with_a_suggestion(engine) -> None:
    _rotated_beam(engine, "mover", 0.0)

    with pytest.raises(ToolError) as exc_info:
        make_parallel(engine, "mover", "ghost")

    assert not isinstance(exc_info.value, KeyError)
    assert exc_info.value.suggestion


def test_aligning_a_nonexistent_object_raises_a_named_error_with_a_suggestion(engine) -> None:
    _rotated_beam(engine, "target", 0.0)

    with pytest.raises(ToolError) as exc_info:
        make_parallel(engine, "ghost", "target")

    assert not isinstance(exc_info.value, KeyError)
    assert exc_info.value.suggestion


def test_measuring_a_nonexistent_object_raises_a_named_error(engine) -> None:
    _rotated_beam(engine, "target", 0.0)

    with pytest.raises(ToolError) as exc_info:
        measure_angle(engine, "ghost", "target")

    assert not isinstance(exc_info.value, KeyError)
    assert exc_info.value.suggestion


# --------------------------------------------------------------------- ALIGN_SPECS


def test_align_specs_are_all_mutating_align_tools() -> None:
    """This package's operations are one-shot corrections applied directly to the scene —
    never exposed to the read-only INSPECT role (ADR-007), always ALIGN per the module's
    own contract."""
    for spec in ALIGN_SPECS:
        assert spec.mutating is True, spec.name
        assert spec.roles == (ToolRole.ALIGN,), spec.name


def test_align_specs_cover_exactly_the_seven_mutating_operations() -> None:
    names = {s.name for s in ALIGN_SPECS}
    assert names == {
        "make_parallel", "make_perpendicular", "make_coplanar",
        "make_plumb", "make_flush", "snap_to_grid", "set_angle",
    }


def test_every_align_spec_has_a_non_empty_input_schema() -> None:
    for spec in ALIGN_SPECS:
        assert spec.input_schema.get("properties"), spec.name
        assert spec.input_schema.get("required"), spec.name


def test_align_result_is_frozen() -> None:
    result = AlignResult(object_id="x", changed=False, angle_before_deg=0.0, angle_after_deg=0.0, detail="")
    with pytest.raises(Exception):
        result.changed = True  # type: ignore[misc]
