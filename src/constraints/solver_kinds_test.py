"""Tests for what ``solve`` computes for each of the twelve ``ConstraintKind`` values.

Solver mechanics (escape hatch, hard/soft, re-solve, batching, errors) live in
``solver_test.py`` — this file is deliberately only about the geometry each constraint
type produces, one test per kind, so a change to one kind's behaviour is never buried in a
file about how solving in general works (see ``CLAUDE.md``).

``up`` is the world-space direction of an object's own local +Z axis; ``forward`` is the
world-space direction of its local +Y axis. A constraint that does not name an axis or an
orientation leaves it exactly as the object's current engine transform already has it —
solving only ever moves what a constraint says it moves.
"""

from __future__ import annotations

import math

import pytest

from contracts import (
    Anchor,
    AnchorKind,
    Constraint,
    ConstraintKind,
    ConstraintSet,
    EPSILON,
    Quat,
    Transform,
    Vec3,
)
from constraints import solve, transform_for


def _rotated_beam(engine, object_id: str, degrees_about_z: float) -> Vec3:
    """A beam elongated along local +Y, rotated about world Z. Returns the resulting
    world-space direction of its own long axis — the "dominant axis" the parallel/
    perpendicular tests measure against."""
    rotation = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(degrees_about_z))
    engine.create_primitive(object_id, "cube", Vec3(0.1, 2.0, 0.1), Transform(rotation=rotation))
    return rotation.rotate(Vec3(0, 1, 0))


def test_on_rests_exactly_on_the_targets_top_surface_from_both_sides(engine) -> None:
    """A generator that gets ``on`` wrong either floats the object above the surface or
    sinks it through — both look like ordinary "resting on the floor" in a thumbnail
    render, which is exactly why this has to be measured rather than eyeballed."""
    engine.create_primitive("floor", "cube", Vec3(4.0, 4.0, 0.2), Transform(translation=Vec3(0, 0, 0)))
    engine.create_primitive("crate", "cube", Vec3(0.5, 0.5, 1.0), Transform(translation=Vec3(0, 0, 5.0)))
    floor_top = engine.world_bounds("floor").maximum.z

    cs = ConstraintSet(
        object_id="crate",
        constraints=(
            Constraint(kind=ConstraintKind.ON, target=Anchor(kind=AnchorKind.FACE, object_id="floor", feature="top")),
        ),
    )

    placement = solve(engine, cs)
    crate_bottom = placement.position.z - 0.5  # half the crate's own height

    assert crate_bottom >= floor_top - EPSILON, "penetrates the floor"
    assert crate_bottom <= floor_top + EPSILON, "floats above the floor"


def test_flush_with_shares_a_face_plane_with_no_gap_or_overlap(engine) -> None:
    """``flush_with`` is what makes two panels read as one continuous wall instead of two
    boxes with a hairline gap or a sliver of overlap — both invisible in a render, both a
    measurable defect."""
    engine.create_primitive("wall_b", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(0, 0, 0)))
    engine.create_primitive("wall_a", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(5.0, 0, 0)))
    wall_b_face_x = engine.world_bounds("wall_b").maximum.x

    cs = ConstraintSet(
        object_id="wall_a",
        constraints=(
            Constraint(kind=ConstraintKind.FLUSH_WITH, target=Anchor(kind=AnchorKind.OBJECT, object_id="wall_b"), axis=Vec3(1, 0, 0)),
        ),
    )

    placement = solve(engine, cs)
    wall_a_face_x = placement.position.x - 0.1  # half wall_a's own thickness

    assert wall_a_face_x == pytest.approx(wall_b_face_x, abs=EPSILON)


def test_centred_on_aligns_named_axes_and_leaves_the_others_untouched(engine) -> None:
    """``centred_on`` names which axes align — a solver that centres every axis regardless
    would make it impossible to centre a sconce horizontally on a wall panel while keeping
    a mounting height an earlier operation already decided."""
    engine.create_primitive("table", "cube", Vec3(1.6, 0.9, 0.75), Transform(translation=Vec3(3.0, 4.0, 5.0)))
    engine.create_primitive("lamp", "cube", Vec3(0.2, 0.2, 0.5), Transform(translation=Vec3(0.0, 0.0, 9.0)))

    cs = ConstraintSet(
        object_id="lamp",
        constraints=(
            Constraint(kind=ConstraintKind.CENTRED_ON, target=Anchor(kind=AnchorKind.OBJECT, object_id="table"), axis=Vec3(1, 1, 0)),
        ),
    )

    placement = solve(engine, cs)

    assert placement.position.x == pytest.approx(3.0, abs=EPSILON)
    assert placement.position.y == pytest.approx(4.0, abs=EPSILON)
    assert placement.position.z == pytest.approx(9.0, abs=EPSILON), "z was not named and must be untouched"


def test_follows_orients_forward_along_the_targets_path_direction(engine) -> None:
    """``follows`` is the primitive behind railings, trims, fences and pipes — an
    instance that does not face along the path it is following is what produces trim with
    a systematically wrong heading, not just per-instance jitter."""
    engine.create_mesh("fence_line", [Vec3(0, 0, 0), Vec3(5.0, 2.0, 0.0)], [])
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 1.0))

    cs = ConstraintSet(
        object_id="post",
        constraints=(
            Constraint(kind=ConstraintKind.FOLLOWS, target=Anchor(kind=AnchorKind.PATH, object_id="fence_line")),
        ),
    )

    placement = solve(engine, cs)

    expected = Vec3(5.0, 2.0, 0.0).normalized()
    assert placement.forward.normalized().as_tuple() == pytest.approx(expected.as_tuple(), abs=1e-3)


def test_offset_from_places_at_exactly_the_requested_distance(engine) -> None:
    """A sconce meant to sit 1.2m proud of a wall face is a defect if it lands at 1.15m or
    1.25m — this is the number the offset was authored against, and it has to come out
    exact, not "close in a render"."""
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(2.0, 0.0, 0.0)))
    engine.create_primitive("sconce", "cube", Vec3(0.1, 0.1, 0.2))

    cs = ConstraintSet(
        object_id="sconce",
        constraints=(
            Constraint(kind=ConstraintKind.OFFSET_FROM, target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"), value=1.2, axis=Vec3(1, 0, 0)),
        ),
    )

    placement = solve(engine, cs)

    assert placement.position.as_tuple() == pytest.approx((3.2, 0.0, 0.0), abs=EPSILON)


def test_ends_at_terminates_exactly_at_the_anchor_not_a_parametric_interval(engine) -> None:
    """A rail that stops at the nearest point on a regular sampling interval rather than
    exactly at the post it is meant to meet leaves either a visible gap or a visible
    overrun — ``ends_at`` exists so a generator never has to guess which interval sample
    happens to land closest."""
    engine.create_primitive("post", "cube", Vec3(0.1, 0.1, 1.0), Transform(translation=Vec3(4.0, 4.0, 0.0)))
    engine.create_primitive("rail", "cube", Vec3(0.05, 2.0, 0.05))

    cs = ConstraintSet(
        object_id="rail",
        constraints=(
            Constraint(kind=ConstraintKind.ENDS_AT, target=Anchor(kind=AnchorKind.OBJECT, object_id="post")),
        ),
    )

    placement = solve(engine, cs)

    assert placement.position.as_tuple() == pytest.approx((4.0, 4.0, 0.0), abs=EPSILON)


def test_plumb_holds_up_vertical_on_a_31_degree_rake(engine) -> None:
    """THE flagship case: posts constrained plumb on a stair rake must stand vertical, not
    lean at the stair's angle. Rise 1.8 over run 3.0 is a 31-degree rake. Aligning an
    instance's up-axis to the path tangent instead of to world up is the single most
    common naive-generator error (``mesh_helpers.rotation_from_up_to``), and it is
    invisible in a thumbnail render."""
    engine.create_mesh("stair_rake", [Vec3(0, 0, 0), Vec3(3.0, 0.0, 1.8)], [])
    engine.create_primitive("baluster", "cube", Vec3(0.03, 0.03, 0.9))

    cs = ConstraintSet(
        object_id="baluster",
        constraints=(
            Constraint(kind=ConstraintKind.FOLLOWS, target=Anchor(kind=AnchorKind.PATH, object_id="stair_rake")),
            Constraint(kind=ConstraintKind.PLUMB, target=Anchor.world_up()),
        ),
    )

    placement = solve(engine, cs)

    assert placement.up.as_tuple() == pytest.approx((0.0, 0.0, 1.0), abs=1e-4)
    rake_tangent = Vec3(3.0, 0.0, 1.8).normalized()
    angle_to_tangent = math.degrees(math.acos(max(-1.0, min(1.0, placement.up.dot(rake_tangent)))))
    assert angle_to_tangent > 25.0, "up ended up parallel to the rake instead of vertical"


def test_without_plumb_following_the_same_rake_may_tilt_up_off_vertical(engine) -> None:
    """The negative half of the flagship case: remove ``plumb`` and keep only ``follows``
    on the identical 31-degree rake. If this produces the same vertical ``up`` as the
    plumb case above, ``plumb`` is decorative and does nothing — this is the test that
    would catch that."""
    engine.create_mesh("stair_rake", [Vec3(0, 0, 0), Vec3(3.0, 0.0, 1.8)], [])
    engine.create_primitive("baluster", "cube", Vec3(0.03, 0.03, 0.9))

    cs = ConstraintSet(
        object_id="baluster",
        constraints=(
            Constraint(kind=ConstraintKind.FOLLOWS, target=Anchor(kind=AnchorKind.PATH, object_id="stair_rake")),
        ),
    )

    placement = solve(engine, cs)

    assert abs(placement.up.z) < 0.99, "up stayed vertical even without plumb; follows alone must be free to tilt it"


def test_parallel_to_aligns_forward_to_zero_degrees(engine) -> None:
    """A 50-degree target angle is deliberately not 0 or 90: a broken implementation that
    just returns the object's original, unrotated heading would be neither parallel nor
    perpendicular to it, and this test catches that where a 0-or-90-degree target would
    not."""
    beam_a_dir = _rotated_beam(engine, "beam_a", 50.0)
    engine.create_primitive("beam_b", "cube", Vec3(0.1, 2.0, 0.1))

    cs = ConstraintSet(
        object_id="beam_b",
        constraints=(
            Constraint(kind=ConstraintKind.PARALLEL_TO, target=Anchor(kind=AnchorKind.OBJECT, object_id="beam_a")),
        ),
    )

    placement = solve(engine, cs)

    dot = placement.forward.normalized().dot(beam_a_dir.normalized())
    assert dot == pytest.approx(1.0, abs=1e-3)


def test_perpendicular_to_aligns_forward_to_ninety_degrees(engine) -> None:
    """Same non-trivial 50-degree target as the parallel case above, so a stub returning
    the object's unrotated heading (cos 50 degrees is far from zero) fails this test too."""
    beam_a_dir = _rotated_beam(engine, "beam_a", 50.0)
    engine.create_primitive("beam_b", "cube", Vec3(0.1, 2.0, 0.1))

    cs = ConstraintSet(
        object_id="beam_b",
        constraints=(
            Constraint(kind=ConstraintKind.PERPENDICULAR_TO, target=Anchor(kind=AnchorKind.OBJECT, object_id="beam_a")),
        ),
    )

    placement = solve(engine, cs)

    dot = placement.forward.normalized().dot(beam_a_dir.normalized())
    assert dot == pytest.approx(0.0, abs=1e-3)


def test_coplanar_with_puts_every_point_of_the_object_in_the_targets_plane(engine) -> None:
    """A sign panel merely close to a wall's plane reads as floating or embedded the
    moment the camera is not perfectly front-on — ``coplanar_with`` is what a flush
    signage or glazing pass depends on being exact, not visually close. The wall is tilted
    15 degrees so an implementation that skips rotation entirely fails immediately."""
    tilt = Quat.from_axis_angle(Vec3(1, 0, 0), math.radians(15))
    engine.create_primitive("wall", "plane", Vec3(4.0, 3.0, 0.0), Transform(rotation=tilt))
    engine.create_primitive("panel", "plane", Vec3(0.6, 0.4, 0.0), Transform(translation=Vec3(9, 9, 9)))
    panel_local_vertices = list(engine.snapshot("panel").vertices)
    wall_point = Vec3(0, 0, 0)
    wall_normal = tilt.rotate(Vec3(0, 0, 1))

    cs = ConstraintSet(
        object_id="panel",
        constraints=(
            Constraint(kind=ConstraintKind.COPLANAR_WITH, target=Anchor(kind=AnchorKind.FACE, object_id="wall", feature="face")),
        ),
    )

    placement = solve(engine, cs)
    transform = transform_for(placement)

    for v in panel_local_vertices:
        world_v = transform.apply(v)
        signed_distance = (world_v - wall_point).dot(wall_normal)
        assert signed_distance == pytest.approx(0.0, abs=1e-3)


def test_spacing_guarantees_the_clear_opening_not_the_centre_to_centre_pitch(engine) -> None:
    """Confusing the clear opening with the centre-to-centre pitch is a real modelling
    bug: a 100mm baluster gap requirement is about the clear span a foot cannot fit
    through, not the distance between baluster centrelines, which is always wider by the
    width of the balusters themselves."""
    engine.create_primitive("neighbour", "cube", Vec3(0.05, 0.2, 1.0), Transform(translation=Vec3(0, 0, 0)))
    engine.create_primitive("baluster", "cube", Vec3(0.05, 0.2, 1.0))
    neighbour_face_x = engine.world_bounds("neighbour").maximum.x

    cs = ConstraintSet(
        object_id="baluster",
        constraints=(
            Constraint(kind=ConstraintKind.SPACING, target=Anchor(kind=AnchorKind.OBJECT, object_id="neighbour"), value=0.1, axis=Vec3(1, 0, 0)),
        ),
    )

    placement = solve(engine, cs)
    baluster_face_x = placement.position.x - 0.025  # half the baluster's own width
    clear_gap = baluster_face_x - neighbour_face_x
    centre_pitch = placement.position.x  # neighbour's centre is at x=0

    assert clear_gap == pytest.approx(0.1, abs=EPSILON)
    assert centre_pitch != pytest.approx(0.1, abs=1e-3), "clear gap and centre-to-centre pitch must not be the same number"


def test_clear_of_pushes_an_overlapping_object_to_the_minimum_distance(engine) -> None:
    """This is the declarative "do not clip": an object placed so it would overlap a
    target must be moved out to the stated clearance, not left interpenetrating because
    nothing else in its constraint set happened to say otherwise."""
    engine.create_primitive("obstruction", "cube", Vec3(1.0, 1.0, 1.0), Transform(translation=Vec3(0, 0, 0)))
    engine.create_primitive("duct", "cube", Vec3(1.0, 1.0, 1.0), Transform(translation=Vec3(0.3, 0, 0)))
    obstruction_face_x = engine.world_bounds("obstruction").maximum.x

    cs = ConstraintSet(
        object_id="duct",
        constraints=(
            Constraint(kind=ConstraintKind.CLEAR_OF, target=Anchor(kind=AnchorKind.OBJECT, object_id="obstruction"), value=0.2, axis=Vec3(1, 0, 0)),
        ),
    )

    placement = solve(engine, cs)
    duct_face_x = placement.position.x - 0.5  # half the duct's own width

    assert duct_face_x >= obstruction_face_x + 0.2 - EPSILON
    assert placement.position.x != pytest.approx(0.3, abs=1e-3), "must have moved away from its overlapping baseline"
