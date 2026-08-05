"""Tests for ``satisfies`` — the per-constraint residual check.

This is what makes a constraint **re-checkable** rather than fire-and-forget: a placement
solved once can be re-measured against the engine's current geometry without a fresh
solve, which is how a caller tells "still valid" from "needs a re-solve" after something
upstream moved, at close to zero cost.
"""

from __future__ import annotations

import pytest

from contracts import (
    Anchor,
    AnchorKind,
    Constraint,
    ConstraintKind,
    ConstraintSet,
    Placement,
    Transform,
    Vec3,
    WORLD_UP,
)
from constraints import satisfies, solve


def test_satisfies_is_empty_when_the_solved_placement_exactly_meets_its_constraints(engine) -> None:
    """An empty residual tuple is the contract's definition of "met exactly"
    (``Placement.residuals`` docstring) — if a placement ``solve`` itself just produced
    fails its own ``satisfies`` check, the two functions disagree about what "solved"
    means and neither can be trusted."""
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(2.0, 0.0, 0.0)))
    engine.create_primitive("sconce", "cube", Vec3(0.1, 0.1, 0.2))
    cs = ConstraintSet(
        object_id="sconce",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.2, axis=Vec3(1, 0, 0),
            ),
        ),
    )

    placement = solve(engine, cs)

    assert satisfies(engine, cs, placement) == ()


def test_satisfies_reports_a_nonzero_residual_for_an_offset_placement(engine) -> None:
    """A caller re-checking a placement it did not just solve — after loading a saved
    scene, say — needs a real number back, not just a boolean, so it can decide whether
    the drift is worth a re-solve."""
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(2.0, 0.0, 0.0)))
    cs = ConstraintSet(
        object_id="sconce",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.2, axis=Vec3(1, 0, 0),
            ),
        ),
    )
    wrong_placement = Placement(
        object_id="sconce", position=Vec3(3.21, 0.0, 0.0), up=WORLD_UP, forward=Vec3(0, 1, 0),
    )

    residuals = satisfies(engine, cs, wrong_placement)

    assert len(residuals) == 1
    assert residuals[0][1] == pytest.approx(0.01, abs=1e-3)


def test_flush_with_a_one_millimetre_error_produces_a_nonzero_residual(engine) -> None:
    """``flush_with`` is a zero-tolerance-by-default hard constraint (``Constraint``'s
    default ``tolerance`` is 1e-4m): a 1mm gap is a visible defect, not a rounding error,
    and ``satisfies`` has to be sensitive enough to catch it."""
    engine.create_primitive("wall_b", "cube", Vec3(0.2, 3.0, 2.5), Transform(translation=Vec3(0, 0, 0)))
    wall_b_face_x = engine.world_bounds("wall_b").maximum.x
    cs = ConstraintSet(
        object_id="wall_a",
        constraints=(
            Constraint(
                kind=ConstraintKind.FLUSH_WITH,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall_b"),
                axis=Vec3(1, 0, 0),
            ),
        ),
    )
    correct_x = wall_b_face_x + 0.1  # wall_a's own half-thickness
    off_by_a_millimetre = Placement(
        object_id="wall_a", position=Vec3(correct_x + 0.001, 0, 0), up=WORLD_UP, forward=Vec3(0, 1, 0),
    )

    residuals = satisfies(engine, cs, off_by_a_millimetre)

    assert len(residuals) == 1
    assert residuals[0][1] == pytest.approx(0.001, abs=1e-4)


def test_satisfies_detects_a_stale_placement_after_the_anchor_moves(engine) -> None:
    """The whole point of storing constraints instead of just applying them once
    (ADR-002): a placement that was correct when solved must read as unsatisfied once its
    anchor has moved, without anyone re-solving first — this is what tells a caller a
    re-solve is due."""
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

    placement = solve(engine, cs)
    assert satisfies(engine, cs, placement) == ()

    engine.set_transform("stair", Transform(translation=Vec3(2.0, 0.0, 1.8)))

    assert satisfies(engine, cs, placement) != ()
