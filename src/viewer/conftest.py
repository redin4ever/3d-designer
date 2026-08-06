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

import asyncio
import json
from contextlib import asynccontextmanager
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


def _move_object(engine, op: Operation) -> OperationResult:
    """Set an object's world transform. Exists so a test can prove a *non-identity*
    transform survives the wire — the identity one every primitive starts at cannot
    distinguish "transform sent correctly" from "transform dropped"."""
    target = op.params["object_id"]
    to = op.params["to"]
    engine.set_transform(target, Transform(translation=Vec3(*to)))
    return OperationResult(op_id=op.op_id, ok=True, modified_objects=(target,))


@pytest.fixture
def viewer_handlers():
    """Enough of a ``HandlerRegistry`` to exercise a real ``scene.Scene`` — mirrors
    ``src/scene/conftest.py``'s own tiny fixture handlers, reimplemented locally so this
    package does not depend on another module's test-only file."""
    return {"add_cube": _add_cube, "delete_object": _delete_object, "move_object": _move_object}


@pytest.fixture
def move_op():
    def _make(op_id: str, object_id: str, to: tuple[float, float, float]) -> Operation:
        return Operation(
            op_id=op_id,
            kind="move_object",
            params={"object_id": object_id, "to": list(to)},
            target_objects=(object_id,),
        )

    return _make


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

    # The two operator channels this feature added. Real enough to observe through the same
    # public `focus` property the real class exposes, rather than only recording calls —
    # `viewer.greeting()` reads it back, and a double that only recorded would let a greeting
    # that never asked still pass.
    def set_focus(self, object_ids) -> None:
        self._focus = tuple(object_ids)
        self.calls.append(("set_focus", (self._focus,)))

    @property
    def focus(self) -> tuple[str, ...]:
        return getattr(self, "_focus", ())

    def add_annotation(self, annotation) -> None:
        self.calls.append(("add_annotation", (annotation,)))


@pytest.fixture
def recording_orchestrator() -> RecordingOrchestrator:
    return RecordingOrchestrator()


class SocketHarness:
    """Everything the real-socket tests need to be deterministic.

    Three rules it exists to enforce, because getting any of them wrong turns a socket
    test into the flaky kind that gets deleted six weeks later:

    1. **Ephemeral ports only** (``port=0``). A fixed port makes two suites — or one suite
       and a developer's running ``forge3d serve`` — fight over the same bind.
    2. **No fixed sleeps.** Synchronisation is always "await the message that proves the
       thing happened", with one outer wall-clock timeout as the backstop. The repo's
       ``--timeout=60`` would kill the whole process, so this budget is well under it.
    3. **Nothing left behind.** Every server and client is closed on the way out, pass or
       fail, so a leaked listener cannot make the *next* test fail instead.

    ``websockets`` is imported inside the methods, not at module scope, so importing this
    conftest — and therefore running every non-socket test in this package — still needs
    no network stack (ADR-008).
    """

    #: Wall-clock budget for one socket test. Comfortably above a loopback round trip and
    #: comfortably below pyproject's ``--timeout=60``, so a hang surfaces as a readable
    #: ``TimeoutError`` in one test rather than as a killed process.
    TIMEOUT = 15.0

    @staticmethod
    def run(main: Callable, timeout: float = TIMEOUT):
        """Run one async test body to completion, or fail it on the budget."""

        async def _bounded():
            return await asyncio.wait_for(main(), timeout)

        return asyncio.run(_bounded())

    @staticmethod
    @asynccontextmanager
    async def serving(scene, orchestrator=None):
        """A started ``ViewerSocketServer`` on an ephemeral loopback port, always closed."""
        from viewer import serve

        server = serve(scene, orchestrator, port=0)
        await server.start()
        try:
            yield server
        finally:
            await server.close()

    @staticmethod
    @asynccontextmanager
    async def client(server):
        """One connected websocket client, always closed."""
        from websockets.asyncio.client import connect

        async with connect(f"ws://127.0.0.1:{server.port}") as ws:
            yield ws

    @staticmethod
    async def recv(ws) -> dict:
        return json.loads(await ws.recv())

    @staticmethod
    async def recv_until(ws, message_type: str, limit: int = 40) -> dict:
        """The next message of ``message_type``, skipping anything before it.

        Skipping rather than asserting on the immediate next message: a test about
        ``HIGHLIGHT`` must not break because ``LOG`` was legitimately added beside it.
        """
        seen: list[str] = []
        for _ in range(limit):
            message = json.loads(await ws.recv())
            seen.append(message["type"])
            if message["type"] == message_type:
                return message
        raise AssertionError(f"never received {message_type!r}; saw {seen}")

    @classmethod
    async def handshake(cls, ws) -> dict:
        """Consume the on-connect messages and return the ``full_scene`` one."""
        return await cls.recv_until(ws, "full_scene")

    @staticmethod
    async def send(ws, message_type: str, data: dict | None = None) -> None:
        await ws.send(json.dumps({"type": message_type, "data": data or {}}))


@pytest.fixture
def sockets() -> type[SocketHarness]:
    return SocketHarness
