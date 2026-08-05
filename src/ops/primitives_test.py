"""Tests for ``add_primitive`` — the one typed, validated way to place a single primitive
mesh.

``add_primitive`` is a throwing stub as of this file (Rule 4 — tests come first); both
tests below are expected to fail with ``NotImplementedError`` until the next pass
implements it.
"""

from __future__ import annotations

import pytest

from contracts import EPSILON, Operation, Vec3
from ops import add_primitive


def test_add_primitive_creates_a_mesh_of_the_requested_size(engine) -> None:
    """A size mismatch here means every downstream operation that assumes this
    primitive's own dimensions (a post's footprint, a tread's depth) is silently wrong
    from the very first object it touches."""
    op = Operation(
        op_id="prim1",
        kind="add_primitive",
        params={"object_id": "block1", "kind": "cube", "size": Vec3(0.4, 0.6, 1.2)},
    )

    result = add_primitive(engine, op)

    obj_id = result.produced_objects[0]
    size = engine.world_bounds(obj_id).size
    assert size.as_tuple() == pytest.approx((0.4, 0.6, 1.2), abs=EPSILON)


def test_add_primitive_names_the_created_object_in_produced_objects(engine) -> None:
    """A caller reading ``produced_objects`` is the only way it learns the id it must use
    to reference this object again — an empty or wrong ``produced_objects`` strands every
    later operation that was meant to target it."""
    op = Operation(
        op_id="prim2",
        kind="add_primitive",
        params={"object_id": "block2", "kind": "cube", "size": Vec3(1, 1, 1)},
    )

    result = add_primitive(engine, op)

    assert len(result.produced_objects) == 1
    assert engine.exists(result.produced_objects[0])
