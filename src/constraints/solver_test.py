"""Tests for the solver's mechanics: escape hatch, hard/soft, re-solve, batching, errors.

Per-``ConstraintKind`` geometric behaviour lives in ``solver_kinds_test.py`` — this file is
deliberately about *how solving behaves*, not what each of the twelve types computes, so a
change to one is never buried in a file about the other (see ``CLAUDE.md``).
"""

from __future__ import annotations

import pytest

from contracts import (
    Anchor,
    AnchorKind,
    Constraint,
    ConstraintError,
    ConstraintKind,
    ConstraintSet,
    CYCLE_RULE,
    Placement,
    Transform,
    Vec3,
    WORLD_UP,
)
from constraints import solve, solve_all, transform_for


def test_escape_hatch_solves_to_exactly_the_raw_position(engine) -> None:
    """The raw-coordinate escape hatch (ADR-004) exists for cases the constraint
    vocabulary cannot express. If solving it produced anything other than the exact
    coordinate supplied, the escape hatch would just be a worse way to say what a
    constraint already says, instead of a genuine fallback."""
    cs = ConstraintSet(object_id="odd_prop", raw_position=Vec3(2.34, 0.0, 1.87))

    placement = solve(engine, cs)

    assert placement.position.as_tuple() == pytest.approx((2.34, 0.0, 1.87))
    assert placement.residuals == ()
    assert placement.satisfied_all_hard is True


def test_hard_constraint_that_cannot_be_met_raises(engine) -> None:
    """A hard constraint expresses a requirement the caller cannot silently ignore
    (``Constraint.hard`` docstring). Two contradictory hard offsets along the same axis
    have no position that satisfies both — returning any placement here would report a
    success that is not true."""
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5))
    cs = ConstraintSet(
        object_id="shelf",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.0, axis=Vec3(1, 0, 0), hard=True,
            ),
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=2.0, axis=Vec3(1, 0, 0), hard=True,
            ),
        ),
    )

    with pytest.raises(ConstraintError):
        solve(engine, cs)


def test_soft_constraint_reports_a_residual_but_all_hard_still_satisfied(engine) -> None:
    """A soft constraint is best-effort by design (``Constraint.hard`` docstring): the
    same contradiction that must raise when both sides are hard must instead resolve the
    hard side exactly and report the soft side's shortfall as a residual — never silently
    dropped, and never escalated into a failure it did not ask to be."""
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5))
    cs = ConstraintSet(
        object_id="shelf",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.0, axis=Vec3(1, 0, 0), hard=True,
            ),
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=2.0, axis=Vec3(1, 0, 0), hard=False,
            ),
        ),
    )

    placement = solve(engine, cs)

    assert placement.satisfied_all_hard is True
    assert len(placement.residuals) == 1
    assert placement.residuals[0][1] == pytest.approx(1.0, abs=1e-3)


def test_resolving_again_after_the_anchor_moves_moves_the_dependent_with_it(engine) -> None:
    """This is the entire reason constraints are stored rather than applied once
    (ADR-002): move the stair, and the railing constrained to it must follow on the next
    solve without anyone re-authoring its constraint set."""
    engine.create_primitive("stair", "cube", Vec3(0.3, 3.0, 0.2), Transform(translation=Vec3(0, 0, 0)))
    engine.create_primitive("railing", "cube", Vec3(0.1, 3.0, 1.0))
    cs = ConstraintSet(
        object_id="railing",
        constraints=(
            Constraint(
                kind=ConstraintKind.CENTRED_ON,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="stair"),
                axis=Vec3(1, 1, 1),
            ),
        ),
    )

    before = solve(engine, cs)
    engine.set_transform("stair", Transform(translation=Vec3(2.0, 0.0, 1.8)))
    after = solve(engine, cs)

    delta = after.position - before.position
    assert delta.as_tuple() == pytest.approx((2.0, 0.0, 1.8), abs=1e-4)


def test_constraint_naming_a_nonexistent_object_raises_with_a_suggestion(engine) -> None:
    """A model that gets an id wrong needs to be told which id and what to try next
    (Gate A 4.2) — a bare ``KeyError`` from deep inside the solver gives it a traceback it
    cannot act on, and it loops on the same broken call."""
    engine.create_primitive("post_1", "cube", Vec3(0.1, 0.1, 1.0))
    cs = ConstraintSet(
        object_id="post_1",
        constraints=(
            Constraint(
                kind=ConstraintKind.ON,
                target=Anchor(kind=AnchorKind.FACE, object_id="deck_9", feature="top"),
            ),
        ),
    )

    with pytest.raises(ConstraintError) as exc:
        solve(engine, cs)
    assert "deck_9" in str(exc.value)
    assert exc.value.suggestion


def test_solve_all_places_targets_before_their_dependents(engine) -> None:
    """``solve_all`` is what an operation calls for a whole batch — if it does not honour
    the same dependency order ``dependency_order`` computes, a batch of N objects is only
    as correct as whichever order it happened to iterate in."""
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5))
    engine.create_primitive("shelf", "cube", Vec3(0.4, 0.3, 0.05))
    wall_cs = ConstraintSet(object_id="wall")
    shelf_cs = ConstraintSet(
        object_id="shelf",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=0.05, axis=Vec3(1, 0, 0),
            ),
        ),
    )

    results = solve_all(engine, [shelf_cs, wall_cs])

    ids = [p.object_id for p in results]
    assert ids.index("wall") < ids.index("shelf")


def test_solve_all_raises_on_a_cycle(engine) -> None:
    """The batch entry point must surface the same cycle failure as ``dependency_order``
    — a caller that only ever calls ``solve_all`` must not need to know a separate
    ordering function exists to be protected from a deadlocked graph."""
    a = ConstraintSet(
        object_id="a",
        constraints=(Constraint(kind=ConstraintKind.FOLLOWS, target=Anchor(kind=AnchorKind.OBJECT, object_id="b")),),
    )
    b = ConstraintSet(
        object_id="b",
        constraints=(Constraint(kind=ConstraintKind.FOLLOWS, target=Anchor(kind=AnchorKind.OBJECT, object_id="a")),),
    )

    with pytest.raises(ConstraintError) as exc:
        solve_all(engine, [a, b])
    assert exc.value.rule == CYCLE_RULE


def test_transform_for_carries_the_placements_position_and_up_axis() -> None:
    """``transform_for`` is the only bridge between a solved ``Placement`` and something
    ``engine.set_transform`` accepts — a caller that solved correctly but gets a wrong
    transform out of this function still ends up with a wrongly placed object."""
    placement = Placement(
        object_id="post", position=Vec3(1.0, 2.0, 3.0), up=WORLD_UP, forward=Vec3(0.0, 1.0, 0.0),
    )

    transform = transform_for(placement)

    assert transform.translation.as_tuple() == pytest.approx((1.0, 2.0, 3.0))
    assert transform.rotation.rotate(Vec3(0, 0, 1)).as_tuple() == pytest.approx(WORLD_UP.as_tuple(), abs=1e-4)
