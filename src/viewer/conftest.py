"""Shared fixtures for ``src/viewer``'s own test suite.

Two kinds of double, same reasoning as ``src/scene/conftest.py`` and
``src/orchestration/conftest.py`` one level up: a real ``scene.Scene`` backed by
``testing.FakeEngine`` for anything that needs genuine geometry (the
queue-survives-a-broken-viewer test, "every object currently in the engine" test — both
need real engine state, not a recording of calls), and lightweight in-memory doubles for
tests that need to construct a specific ``contracts.SceneChangeEvent`` directly (the
per-``ChangeKind`` wire-mapping tests, since the real ``scene.apply`` today never emits
``TRANSFORMS_ONLY``/``TOPOLOGY_CHANGED`` — see ``README.md``'s "Assumptions") or assert a
routing call was made with the argument the wire protocol implies.

Local to ``src/viewer/``; the root ``engine`` fixture (``FakeEngine``) is not redefined
here.
"""

from __future__ import annotations

from typing import Callable

import pytest

from contracts import (
    MeshSnapshot,
    Operation,
    OperationResult,
    RunState,
    SceneChangeEvent,
    Transform,
    Vec3,
)
from scene import Scene


def _add_cube(engine, op: Operation) -> OperationResult:
    name = op.params["name"]
    oid = engine.create_primitive(name, "cube", Vec3(1.0, 1.0, 1.0))
    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(oid,))


def _delete_object(engine, op: Operation) -> OperationResult:
    target = op.params["object_id"]
    engine.delete(target)
    return OperationResult(op_id=op.op_id, ok=True, removed_objects=(target,))


@pytest.fixture
def viewer_handlers():
    """Enough of a ``HandlerRegistry`` to exercise a real ``scene.Scene`` — mirrors
    ``src/scene/conftest.py``'s own tiny fixture handlers, reimplemented locally so this
    package does not depend on another module's test-only file."""
    return {"add_cube": _add_cube, "delete_object": _delete_object}


@pytest.fixture
def add_cube_op():
    def _make(op_id: str, name: str) -> Operation:
        return Operation(op_id=op_id, kind="add_cube", params={"name": name})

    return _make


@pytest.fixture
def delete_op():
    def _make(op_id: str, object_id: str) -> Operation:
        return Operation(
            op_id=op_id,
            kind="delete_object",
            params={"object_id": object_id},
            target_objects=(object_id,),
        )

    return _make


@pytest.fixture
def real_scene(engine, viewer_handlers) -> Scene:
    """A genuine ``scene.Scene`` over ``testing.FakeEngine`` — real geometry, not a
    recording of calls, for the tests that need to prove the geometry core actually
    survives, or that enumeration reflects real engine state."""
    return Scene(engine, viewer_handlers)


@pytest.fixture
def make_snapshot():
    """Factory: ``make_snapshot("crate")`` builds a minimal, valid one-triangle
    ``MeshSnapshot`` for tests that only care about the transform or the object id."""

    def _make(object_id: str = "obj", **overrides) -> MeshSnapshot:
        defaults = dict(
            object_id=object_id,
            vertices=[Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)],
            triangles=[(0, 1, 2)],
            transform=Transform(),
        )
        defaults.update(overrides)
        return MeshSnapshot(**defaults)

    return _make


class FakeScene:
    """A minimal in-memory double for ``scene``'s public surface, real enough to publish
    an arbitrary ``SceneChangeEvent`` on demand — which the real ``scene.Scene`` cannot do
    for ``ChangeKind.TRANSFORMS_ONLY``/``TOPOLOGY_CHANGED`` today. Also records
    ``undo``/``rollback_to`` calls for the routing tests: same reasoning as
    ``testing.FakeEngine.calls``'s own docstring — some assertions are inherently about
    which call was made, not about an observable geometry difference.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._listeners: list[Callable[[SceneChangeEvent], None]] = []
        self._snapshots: dict[str, MeshSnapshot] = {}
        self._object_ids: tuple[str, ...] = ()

    def set_objects(self, *snapshots: MeshSnapshot) -> None:
        self._object_ids = tuple(s.object_id for s in snapshots)
        self._snapshots = {s.object_id: s for s in snapshots}

    def list_objects(self) -> tuple[str, ...]:
        return self._object_ids

    def snapshot_of(self, object_id: str) -> MeshSnapshot:
        return self._snapshots[object_id]

    def subscribe(self, listener: Callable[[SceneChangeEvent], None]):
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsubscribe

    def publish(self, event: SceneChangeEvent) -> None:
        """Simulate ``scene``'s own ``_emit``: deliver to every current subscriber."""
        for listener in list(self._listeners):
            listener(event)

    def undo(self, steps: int = 1):
        self.calls.append(("undo", (steps,)))

    def rollback_to(self, checkpoint: str):
        self.calls.append(("rollback_to", (checkpoint,)))


@pytest.fixture
def fake_scene() -> FakeScene:
    return FakeScene()


class RecordingOrchestrator:
    """A minimal double for ``orchestration.Orchestrator``'s run-control surface. Real
    enough to observe state transitions through the same public ``state`` property the
    real class exposes, rather than only recording calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.notes: list[str] = []
        self.cadence = None
        self._state = RunState.RUNNING

    @property
    def state(self) -> RunState:
        return self._state

    def pause(self) -> None:
        self._state = RunState.PAUSED
        self.calls.append(("pause", ()))

    def resume(self) -> None:
        self._state = RunState.RUNNING
        self.calls.append(("resume", ()))

    def set_cadence(self, cadence) -> None:
        self.cadence = cadence
        self.calls.append(("set_cadence", (cadence,)))

    def add_operator_note(self, text: str) -> None:
        self.notes.append(text)
        self.calls.append(("add_operator_note", (text,)))


@pytest.fixture
def recording_orchestrator() -> RecordingOrchestrator:
    return RecordingOrchestrator()
