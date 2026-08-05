"""Tests for ``dependency_order`` — safe solving order and cycle detection.

Solving out of order reads a target's pre-solve position and produces a placement that
looks fine until the object it depends on moves again — a wrong-but-plausible result,
which is the worst kind. A cycle must fail loudly rather than let one side solve against
stale geometry (Gate A 4.2); a diamond, which only *looks* dangerous because two nodes
share a target, must not be rejected by mistake.
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
    Vec3,
)
from constraints import dependency_order


def _offset(object_id: str, target: str, axis: Vec3 = Vec3(1, 0, 0), value: float = 1.0) -> ConstraintSet:
    """A minimal single-dependency constraint set: ``object_id`` targets ``target``."""
    return ConstraintSet(
        object_id=object_id,
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id=target),
                value=value,
                axis=axis,
            ),
        ),
    )


def test_dependency_order_puts_a_target_before_its_dependent() -> None:
    """A shelf solved before the wall it is offset from reads the wall's stale position —
    the exact bug this ordering exists to prevent."""
    wall = ConstraintSet(object_id="wall")
    shelf = _offset("shelf", "wall")

    order = dependency_order([shelf, wall])

    assert order.index("wall") < order.index("shelf")


def test_dependency_order_is_a_permutation_of_every_input_object() -> None:
    """Silently dropping an object from the order is worse than a wrong order — the
    caller would solve every *other* object correctly and never notice one went
    unsolved (Rule 6: silence and success must not be the same shape)."""
    sets = [ConstraintSet(object_id="a"), _offset("b", "a"), _offset("c", "b")]

    order = dependency_order(sets)

    assert set(order) == {"a", "b", "c"}
    assert len(order) == 3


def test_two_node_mutual_follow_is_a_cycle() -> None:
    """``A follows B`` and ``B follows A`` in the same scene is the smallest possible
    deadlock — neither can be solved first without reading the other's stale geometry."""
    a = _offset("a", "b")
    b = _offset("b", "a")

    with pytest.raises(ConstraintError) as exc:
        dependency_order([a, b])
    assert exc.value.rule == CYCLE_RULE


def test_three_node_cycle_is_detected() -> None:
    """A longer cycle is the same failure one hop further away — a solver that only
    checks direct mutual pairs would miss this and attempt to solve it anyway."""
    a = _offset("a", "b")
    b = _offset("b", "c")
    c = _offset("c", "a")

    with pytest.raises(ConstraintError) as exc:
        dependency_order([a, b, c])
    assert exc.value.rule == CYCLE_RULE


def test_diamond_shared_target_is_not_a_cycle_and_solves() -> None:
    """A rail post constrained to two different reference edges of the same stair is a
    diamond, not a cycle — rejecting it would make an entirely ordinary, solvable
    constraint set unusable."""
    d = ConstraintSet(object_id="d")
    b = _offset("b", "d")
    c = _offset("c", "d", axis=Vec3(0, 1, 0))
    a = ConstraintSet(
        object_id="a",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="b"),
                value=0.5, axis=Vec3(1, 0, 0),
            ),
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="c"),
                value=0.5, axis=Vec3(0, 1, 0),
            ),
        ),
    )

    order = dependency_order([a, b, c, d])

    assert order.index("d") < order.index("b")
    assert order.index("d") < order.index("c")
    assert order.index("b") < order.index("a")
    assert order.index("c") < order.index("a")
