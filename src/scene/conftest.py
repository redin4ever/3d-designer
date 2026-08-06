"""Shared test fixtures for ``scene``: a tiny fake handler registry.

``scene`` must be testable without ``src/ops/`` existing (it does not yet — see
``.pipeline/modules.json``, where ``scene`` lists ``ops``/``align``/``gaps``/``detail``/
``uv`` only as eventual, design-time dependencies). These handlers are the whole surface
every test file in this package needs: one that creates a named cube, one that deletes an
object, one that moves an existing object (the *targeting* shape — it fails loudly when its
target is absent), one that always raises, and one that is deliberately **non-deterministic**
for the undo-barrier tests. None of them import anything outside ``contracts``.

Local to ``src/scene/`` — pytest picks up a nested ``conftest.py`` automatically. The root
``engine`` fixture (``conftest.py`` at the repo root) is not redefined here.
"""

from __future__ import annotations

from itertools import count

import pytest

from contracts import (
    EngineProtocol,
    HandlerRegistry,
    Operation,
    OperationResult,
    Transform,
    Vec3,
)


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


def _move_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Move an object that must already exist.

    Distinct from ``_delete_object`` in one way that matters: it reaches the engine without
    an ``exists`` guard, so a missing target surfaces as a raised ``EngineError`` rather
    than a returned ``ok=False``. ``replay`` has to survive both shapes, and only two
    handlers can prove it does.
    """
    target = op.params["object_id"]
    engine.set_transform(target, Transform(translation=Vec3(*op.params.get("to", (0.0, 0.0, 0.0)))))
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=(target,))


def _boom(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise RuntimeError("handler exploded")


_RANDOM_NAMES = count(1)


def _random_object(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Create an object whose name is different on every single call.

    This stands in for ``raw_execute`` running an arbitrary script (ADR-009), and its
    non-determinism is the *point*: it is the only kind of handler whose output can tell a
    genuine snapshot restore apart from a silent re-run. A deterministic handler produces
    identical geometry either way, which is exactly why the re-run bug survived a green
    suite.

    A counter rather than ``uuid4`` so the suite itself stays deterministic
    (``.claude/rules/testing.md``): every *call* differs, every *run* is reproducible.
    """
    name = f"randobj_{next(_RANDOM_NAMES):06d}"
    oid = engine.create_primitive(name, "cube", Vec3(1.0, 1.0, 1.0))
    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(oid,))


@pytest.fixture
def handlers() -> HandlerRegistry:
    """A registry with exactly the operation kinds these tests need: ``add_cube``,
    ``delete_object``, ``move_object`` (targets existing geometry and raises when it is
    gone), ``boom`` (always raises, for the failure-path tests) and ``random_object`` (a
    stand-in for raw execution — never produces the same thing twice). Real enough to
    produce and remove real ``FakeEngine`` geometry — not a mock that only records calls."""
    return {
        "add_cube": _add_cube,
        "delete_object": _delete_object,
        "move_object": _move_object,
        "boom": _boom,
        "random_object": _random_object,
    }


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


@pytest.fixture
def move_op():
    """Factory: ``move_op("op1", "a", (1, 0, 0))`` builds an ``Operation`` the
    ``move_object`` handler understands. Declares ``target_objects``, so it is the fixture
    the target-validation tests are written against."""

    def _make(op_id: str, object_id: str, to: tuple[float, float, float] = (1.0, 0.0, 0.0)):
        return Operation(
            op_id=op_id,
            kind="move_object",
            params={"object_id": object_id, "to": list(to)},
            target_objects=(object_id,),
        )

    return _make


@pytest.fixture
def random_object_op():
    """Factory: ``random_object_op("op1")`` builds the opaque, non-deterministic operation
    that stands in for a raw-execution barrier (ADR-009)."""

    def _make(op_id: str) -> Operation:
        return Operation(op_id=op_id, kind="random_object", opaque=True)

    return _make
