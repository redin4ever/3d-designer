"""Tests for ``add_staircase`` — a straight run of treads at a given rise, run and width.

``add_staircase`` is a throwing stub as of this file (Rule 4 — tests come first); every
test below is expected to fail with ``NotImplementedError`` until the next pass implements
it. Every assertion here is on the built geometry's own world bounds, never on the
parameters handed in, per the module's own docstring: a handler can validate a parameter
and still build the wrong thing.
"""

from __future__ import annotations

import pytest

from contracts import EPSILON, Operation
from ops import add_staircase


def test_staircase_produces_exactly_the_requested_number_of_treads(engine) -> None:
    """A staircase short a tread is a step a person's foot will not find; one tread over
    is a step nobody expects to be there. Both are counted from the built objects
    themselves, not the ``treads`` parameter that was merely requested."""
    op = Operation(
        op_id="stair1",
        kind="add_staircase",
        params={"object_id": "stair1", "treads": 6, "rise": 0.18, "run": 0.28, "width": 1.0},
    )

    result = add_staircase(engine, op)

    treads = [pid for pid in result.produced_objects if "_tread_" in pid]
    assert len(treads) == 6


def test_total_rise_equals_treads_times_rise_per_tread(engine) -> None:
    """A stair that reaches a landing above or below the floor it is meant to meet is a
    code violation, not a cosmetic defect — checked here on the highest tread's own world
    top surface, never on the ``rise``/``treads`` params that were merely requested."""
    treads, rise, run = 8, 0.18, 0.28
    op = Operation(
        op_id="stair2",
        kind="add_staircase",
        params={"object_id": "stair2", "treads": treads, "rise": rise, "run": run, "width": 1.0},
    )

    result = add_staircase(engine, op)

    tread_ids = result.produced_objects
    highest_top = max(engine.world_bounds(pid).maximum.z for pid in tread_ids)
    assert highest_top == pytest.approx(treads * rise, abs=EPSILON)


def test_each_tread_top_surface_is_exactly_one_rise_above_the_one_below(engine) -> None:
    """A generator that gets tread-to-tread rise even slightly wrong produces a stair that
    is a genuine trip hazard — human gait expects every riser to be identical, and a 6mm
    inconsistency is the threshold building codes treat as dangerous. Measured on
    consecutive treads' own world top surfaces, in climb order."""
    treads, rise, run = 5, 0.2, 0.3
    op = Operation(
        op_id="stair3",
        kind="add_staircase",
        params={"object_id": "stair3", "treads": treads, "rise": rise, "run": run, "width": 1.0},
    )

    result = add_staircase(engine, op)

    tops = sorted(engine.world_bounds(pid).maximum.z for pid in result.produced_objects)
    for lower, upper in zip(tops, tops[1:]):
        assert upper - lower == pytest.approx(rise, abs=EPSILON)
