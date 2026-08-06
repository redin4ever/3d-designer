"""Gate A 4.2 for the *geometry* half of this module: degenerate input names a rule.

Gate A 4.2, in the user's own words, is that a failing agent is told **what rule it broke**.
Phase 6 found that promise kept for validation failures and broken for geometric ones:
``constraints`` raises a well-formed :class:`~contracts.ConstraintError` for an unknown
object, a bad index and a cycle, and then lets a degenerate vector reach
``contracts.Vec3.normalized()`` — which raises ``ValueError: cannot normalize a zero-length
vector`` from a file the agent has never seen, with no rule, no parameter name and no
suggestion.

The consequence is specific and measured elsewhere in the product's own research: an agent
handed an opaque error retries the identical failing call. A traceback pointing at
``contracts/geometry.py`` does not tell it that ``Constraint.axis`` was the problem, which of
its constraints carried it, or that ``axis`` is a direction rather than a bitmask
(``CLAUDE.md``) — the single most likely reason it built a zero one.

Every test here therefore asserts three things, not one: that a :class:`~contracts.RuleError`
-shaped failure arrives, that it names a rule, and that it suggests something the agent can
act on. A named error with an empty ``suggestion`` is the same failure wearing a better hat
(``contracts.errors.RuleError``'s own docstring says so).
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
    Vec3,
)
from constraints import solve

from constraints._orientation import forward_for, up_for
from constraints._position import PositionEffect, apply_position_effect, position_effect


ZERO = Vec3(0.0, 0.0, 0.0)


def _wall(engine) -> None:
    engine.create_primitive("wall", "cube", Vec3(0.2, 3.0, 2.5))


# --- the public path: a zero Constraint.axis --------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        ConstraintKind.OFFSET_FROM,
        ConstraintKind.FLUSH_WITH,
        ConstraintKind.SPACING,
        ConstraintKind.CLEAR_OF,
    ],
)
def test_a_zero_axis_on_an_axis_parameterised_constraint_names_the_rule(engine, kind) -> None:
    """``Constraint.axis`` is a *direction* for this family and a component-wise mask only
    for ``centred_on`` (``CLAUDE.md``) — which is exactly the confusion that produces a zero
    axis: an agent that thinks in masks writes ``Vec3(0, 0, 0)`` meaning "no axis".

    Today that reaches ``Vec3.normalized()`` and comes back as a traceback naming
    ``contracts/geometry.py``, so the agent cannot tell which of its constraints was wrong,
    or that the field means something different from what it assumed. It retries, unchanged.
    """
    _wall(engine)
    cs = ConstraintSet(
        object_id="shelf",
        constraints=(
            Constraint(
                kind=kind,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.0,
                axis=ZERO,
            ),
        ),
    )

    with pytest.raises(ConstraintError) as caught:
        solve(engine, cs)

    error = caught.value
    assert error.rule, "a geometry failure with no rule is the thing Gate A 4.2 forbids"
    assert error.suggestion, "an agent given no next step retries the same call"
    assert "axis" in error.detail.lower(), (
        f"the detail must name the offending parameter, not just the failure: {error.detail!r}"
    )
    assert kind.value in error.detail, (
        f"the detail must identify which constraint carried it: {error.detail!r}"
    )


def test_the_zero_axis_error_names_the_object_and_the_target(engine) -> None:
    """Naming the rule is not enough when a set carries several constraints: the agent has
    to know *which* one to change. An error that says "a zero axis" and nothing else turns a
    one-line fix into a bisect over the whole constraint set."""
    _wall(engine)
    cs = ConstraintSet(
        object_id="shelf",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.0,
                axis=ZERO,
            ),
        ),
    )

    with pytest.raises(ConstraintError) as caught:
        solve(engine, cs)

    assert "shelf" in caught.value.detail
    assert "wall" in caught.value.detail


def test_a_usable_axis_still_solves(engine) -> None:
    """The guard must reject only what is genuinely unusable. A guard that also caught
    ordinary directions would turn every ``offset_from`` into a failure — the regression that
    matters most here, because it would be reported as "the solver is broken", not as "the
    guard is too tight"."""
    _wall(engine)
    cs = ConstraintSet(
        object_id="shelf",
        constraints=(
            Constraint(
                kind=ConstraintKind.OFFSET_FROM,
                target=Anchor(kind=AnchorKind.OBJECT, object_id="wall"),
                value=1.0,
                axis=Vec3(1.0, 0.0, 0.0),
            ),
        ),
    )

    placement = solve(engine, cs)

    assert placement.position.x == pytest.approx(1.0)


# --- the internal dispatch guards -------------------------------------------------------
#
# These three raise on a constraint kind that the family does not handle. `solve` dispatches
# by membership in POSITION_KINDS / FORWARD_KINDS / UP_KINDS, so no agent input reaches them
# today — they fire when a *new* ConstraintKind is added and one of the three sets is not
# updated with it. That makes them the first thing a future contributor sees, which is
# exactly why the message has to say what to do rather than restate the kind's name.


def test_asking_a_non_forward_kind_for_a_forward_direction_names_the_rule(engine) -> None:
    """The thirteenth constraint kind is the case this guard exists for. If it surfaces as a
    bare ``ValueError``, the contributor who added it gets "``<ConstraintKind.ON: 'on'>``
    does not set forward" and has to go read three modules to find out which set to add it
    to."""
    constraint = Constraint(
        kind=ConstraintKind.ON, target=Anchor(kind=AnchorKind.OBJECT, object_id="wall")
    )

    with pytest.raises(ConstraintError) as caught:
        forward_for(engine, constraint)

    assert caught.value.rule
    assert caught.value.suggestion


def test_asking_a_non_up_kind_for_an_up_direction_names_the_rule(engine) -> None:
    """As above, for the ``up``-setting family. Same failure, same reader, same need."""
    constraint = Constraint(
        kind=ConstraintKind.ON, target=Anchor(kind=AnchorKind.OBJECT, object_id="wall")
    )

    with pytest.raises(ConstraintError) as caught:
        up_for(engine, constraint)

    assert caught.value.rule
    assert caught.value.suggestion


def test_asking_a_non_position_kind_for_a_position_effect_names_the_rule(engine) -> None:
    """The position family's own dispatch guard. ``residual.satisfies`` calls
    ``position_effect`` too, so an unhandled kind fails in two places at once and both need
    to say the same thing."""
    _wall(engine)
    constraint = Constraint(
        kind=ConstraintKind.PLUMB, target=Anchor(kind=AnchorKind.OBJECT, object_id="wall")
    )

    with pytest.raises(ConstraintError) as caught:
        position_effect(engine, "shelf", constraint, ZERO)

    assert caught.value.rule
    assert caught.value.suggestion


def test_applying_an_effect_with_an_unusable_axis_names_the_rule() -> None:
    """``apply_position_effect`` and ``position_residual`` are the two functions
    ``solver.py`` and ``residual.py`` share so they cannot disagree about what a constraint
    demands.

    A ``PositionEffect`` carrying a zero axis reaches ``normalized()`` in both, so the same
    unnamed traceback would arrive from two different call paths — and a stored
    ``Placement`` being re-checked (``satisfies``) is the path where the agent is furthest
    from the constraint that caused it.
    """
    with pytest.raises(ConstraintError) as caught:
        apply_position_effect(Vec3(1.0, 2.0, 3.0), PositionEffect(axis=ZERO, scalar=5.0))

    assert caught.value.rule
    assert caught.value.suggestion
