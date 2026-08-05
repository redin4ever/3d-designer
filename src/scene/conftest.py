"""Shared test fixtures for ``scene``: a tiny fake handler registry.

``scene`` must be testable without ``src/ops/`` existing (it does not yet — see
``.pipeline/modules.json``, where ``scene`` lists ``ops``/``align``/``gaps``/``detail``/
``uv`` only as eventual, design-time dependencies). These handlers are the whole surface
every test file in this package needs: one that creates a named cube, one that deletes an
object, and one that always raises (for the failure-path tests). None of them import
anything outside ``contracts``.

Local to ``src/scene/`` — pytest picks up a nested ``conftest.py`` automatically. The root
``engine`` fixture (``conftest.py`` at the repo root) is not redefined here.
"""

from __future__ import annotations

import pytest

from contracts import EngineProtocol, HandlerRegistry, Operation, OperationResult, Vec3


def _add_cube(engine: EngineProtocol, op: Operation) -> OperationResult:
    name = op.params["name"]
    size = op.params.get("size", 1.0)
    if engine.exists(name):
        return OperationResult(
            op_id=op.op_id,
            ok=False,
            error_rule="scene_test.duplicate_object",
            error_detail=f"{name!r} already exists",
        )
    oid = engine.create_primitive(name, "cube", Vec3(size, size, size))
    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(oid,))


def _delete_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    target = op.params["object_id"]
    if not engine.exists(target):
        return OperationResult(
            op_id=op.op_id,
            ok=False,
            error_rule="scene_test.no_such_object",
            error_detail=f"{target!r} does not exist",
        )
    engine.delete(target)
    return OperationResult(op_id=op.op_id, ok=True, removed_objects=(target,))


def _boom(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise RuntimeError("handler exploded")


@pytest.fixture
def handlers() -> HandlerRegistry:
    """A registry with exactly the operation kinds these tests need: ``add_cube``,
    ``delete_object``, and ``boom`` (always raises, for the failure-path tests). Real
    enough to produce and remove real ``FakeEngine`` geometry — not a mock that only
    records calls."""
    return {"add_cube": _add_cube, "delete_object": _delete_object, "boom": _boom}


@pytest.fixture
def add_cube_op():
    """Factory: ``add_cube_op("op1", "a")`` builds an ``Operation`` the ``add_cube``
    handler understands."""

    def _make(op_id: str, name: str, *, size: float = 1.0, opaque: bool = False) -> Operation:
        return Operation(
            op_id=op_id,
            kind="add_cube",
            params={"name": name, "size": size},
            opaque=opaque,
        )

    return _make


@pytest.fixture
def delete_op():
    """Factory: ``delete_op("op1", "a")`` builds an ``Operation`` the ``delete_object``
    handler understands."""

    def _make(op_id: str, object_id: str) -> Operation:
        return Operation(
            op_id=op_id,
            kind="delete_object",
            params={"object_id": object_id},
            target_objects=(object_id,),
        )

    return _make
