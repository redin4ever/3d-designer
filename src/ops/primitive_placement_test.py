"""A parameter the handler supports and the schema hides is a parameter that does not exist.

`add_primitive`'s handler has always accepted an optional `transform`; its published
`input_schema` never declared one. An agent acts on the schema alone, so every primitive
anyone ever asked for arrived at the world origin — half-buried in whatever floor was
already there — and the only way out was an `align` tool from a later phase.
"""

from __future__ import annotations

from contracts import Operation, Transform, Vec3
from testing import FakeEngine

from ops import OP_SPECS, add_primitive


def _spec(name: str):
    return next(s for s in OP_SPECS if s.name == name)


def test_the_schema_declares_the_transform_the_handler_accepts() -> None:
    """The defect itself. Nothing else in this suite could see it: the handler test passed
    because it called the handler directly, and the schema test passed because it only
    checked the parameters the schema listed."""
    props = _spec("add_primitive").input_schema["properties"]
    assert "transform" in props, "an agent cannot place a primitive it cannot position"


def test_the_declared_transform_is_the_shape_the_boundary_actually_coerces() -> None:
    """A schema that declares a different shape from the one `app.handlers` converts is
    worse than no schema: the agent follows it and the call fails at the boundary."""
    transform = _spec("add_primitive").input_schema["properties"]["transform"]
    assert set(transform["properties"]) == {"translation", "rotation", "scale"}
    assert transform["properties"]["rotation"]["minItems"] == 4, "quaternion, not euler"


def test_a_placed_primitive_lands_where_it_was_asked_to() -> None:
    """The consequence, end to end."""
    engine = FakeEngine()
    add_primitive(
        engine,
        Operation(
            op_id="op1",
            kind="add_primitive",
            params={
                "object_id": "crate",
                "kind": "cube",
                "size": Vec3(1.0, 1.0, 1.0),
                "transform": Transform(translation=Vec3(2.0, 3.0, 4.0)),
            },
        ),
    )
    bounds = engine.world_bounds("crate")
    assert abs(bounds.centre.x - 2.0) < 1e-6, f"landed at {bounds.centre.as_tuple()}"
    assert abs(bounds.centre.y - 3.0) < 1e-6
    assert abs(bounds.centre.z - 4.0) < 1e-6


def test_omitting_the_transform_still_works() -> None:
    """It is optional, and every existing caller omits it."""
    engine = FakeEngine()
    result = add_primitive(
        engine,
        Operation(
            op_id="op1",
            kind="add_primitive",
            params={"object_id": "crate", "kind": "cube", "size": Vec3(1.0, 1.0, 1.0)},
        ),
    )
    assert result.ok
