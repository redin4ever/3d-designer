"""A real WebSocket server, on a real ephemeral loopback port, with real clients.

Every other test in this package stops at the bridge's outbound queue. That queue has
never been connected to a socket by a test, which means the one capability the live view
exists to provide — *a browser somewhere sees the scene change* — had zero runs behind it
while the module was marked GREEN. A message correctly queued and never sent looks
identical to a working product from inside ``bridge_test.py``.

These tests bind a socket, connect a client written against ``contracts.wire``'s JSON
shape (the same shape ``frontend/src/socket.js`` parses), and assert on what actually
arrives. Synchronisation is always "await the message that proves it happened" — never a
sleep — and the harness in ``conftest.py`` owns the ephemeral port and the teardown.
"""

from __future__ import annotations

import socket as socketlib

from contracts import ChangeKind, CheckCadence, RunState, SceneChangeEvent

from viewer import ViewerBridge


def test_a_connecting_client_receives_the_current_scene(sockets, real_scene, add_cube_op) -> None:
    """A browser opened halfway through a build must see everything already made, not
    only what happens next. This is the whole first frame."""
    real_scene.apply(add_cube_op("op1", "wall_a"))
    real_scene.apply(add_cube_op("op2", "wall_b"))

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                full = await sockets.handshake(ws)
        return full

    full = sockets.run(main)

    assert set(full["object_ids"]) == {"wall_a", "wall_b"}
    assert {m["object_id"] for m in full["meshes"]} == {"wall_a", "wall_b"}
    assert {t["object_id"] for t in full["transforms"]} == {"wall_a", "wall_b"}


def test_a_geometry_change_reaches_a_connected_client_with_its_real_transform(
    sockets, real_scene, add_cube_op, move_op
) -> None:
    """The P0 this test exists for: the browser once rendered every object at the world
    origin because the transform never made it across. A mesh at the wrong place is worse
    than no mesh — it looks like a modelling bug and sends the agent fixing geometry that
    was already correct.
    """

    async def main():
        real_scene.apply(add_cube_op("op1", "crate"))
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                real_scene.apply(move_op("op2", "crate", (2.0, -3.5, 4.25)))
                return await sockets.recv_until(ws, "mesh_upsert")

    message = sockets.run(main)

    assert message["object_ids"] == ["crate"]
    (transform,) = message["transforms"]
    assert transform["object_id"] == "crate"
    assert transform["position"] == [2.0, -3.5, 4.25]
    assert transform["quaternion"] == [0.0, 0.0, 0.0, 1.0]  # x,y,z,w — three.js order


def test_two_clients_connected_at_once_both_receive_the_same_change(
    sockets, real_scene, add_cube_op
) -> None:
    """Gate A 10.1 — many watchers. A second operator opening the page must not silently
    take the feed away from the first, and must not get a private copy of the run."""

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as first, sockets.client(server) as second:
                await sockets.handshake(first)
                await sockets.handshake(second)
                assert server.client_count == 2

                real_scene.apply(add_cube_op("op1", "beam"))

                return (
                    await sockets.recv_until(first, "mesh_upsert"),
                    await sockets.recv_until(second, "mesh_upsert"),
                )

    to_first, to_second = sockets.run(main)

    assert to_first["object_ids"] == ["beam"]
    assert to_second["object_ids"] == ["beam"]
    assert to_first["seq"] == to_second["seq"]  # one counter, one truth, two watchers


def test_a_client_that_dies_mid_broadcast_does_not_take_down_the_server(
    sockets, real_scene, add_cube_op
) -> None:
    """One watcher closing a laptop lid must not stop the run for anybody else.

    The dead client is injected directly into the connection set rather than being a real
    socket that was politely closed: a clean close is already removed from the set before
    the next broadcast, so it would exercise nothing. What has to hold is that a *send*
    which raises is contained — that is the case a half-open TCP connection produces, and
    it is the one that would otherwise abort the loop mid-fanout and leave every client
    after it in the iteration order silently stale.
    """

    class DeadClient:
        async def send(self, _payload) -> None:
            raise ConnectionResetError("half-open connection")

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                dead = DeadClient()
                server._clients.add(dead)

                real_scene.apply(add_cube_op("op1", "beam"))
                delivered = await sockets.recv_until(ws, "mesh_upsert")

                # still serving: a brand-new client can still connect and be served
                async with sockets.client(server) as late:
                    late_full = await sockets.handshake(late)

                return delivered, late_full, dead in server._clients

    delivered, late_full, dead_still_registered = sockets.run(main)

    assert delivered["object_ids"] == ["beam"]
    assert late_full["object_ids"] == ["beam"]
    assert dead_still_registered is False  # dropped, not retried forever


def test_a_client_disconnecting_leaves_the_server_and_the_other_client_alive(
    sockets, real_scene, add_cube_op
) -> None:
    """The ordinary version of the same guarantee, with two genuine sockets: one closes,
    the other keeps receiving, and the server stops counting the one that left."""

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as stays:
                async with sockets.client(server) as leaves:
                    await sockets.handshake(stays)
                    await sockets.handshake(leaves)
                    assert server.client_count == 2

                real_scene.apply(add_cube_op("op1", "beam"))
                survived = await sockets.recv_until(stays, "mesh_upsert")

                # the departed client is reaped: proven by a message that only reaches
                # the survivor, not by waiting a fixed time for a close frame
                real_scene.apply(add_cube_op("op2", "post"))
                await sockets.recv_until(stays, "mesh_upsert")
                return survived, server.client_count

    survived, remaining = sockets.run(main)

    assert survived["object_ids"] == ["beam"]
    assert remaining == 1


def test_an_inbound_cadence_change_reaches_the_orchestrator(
    sockets, real_scene, recording_orchestrator
) -> None:
    """The operator controls (Gate A 5.4) are only real if the message survives the trip
    inbound too. ``SET_CADENCE`` answers nothing, so the barrier is the *next* request's
    reply — one connection is one ordered stream, so a ``full_scene`` in hand proves the
    cadence change was already applied. No sleep, no polling."""

    async def main():
        async with sockets.serving(real_scene, recording_orchestrator) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                await sockets.send(ws, "set_cadence", {"cadence": "phase_boundaries"})
                await sockets.send(ws, "request_full_scene")
                await sockets.recv_until(ws, "full_scene")

    sockets.run(main)

    assert recording_orchestrator.cadence is CheckCadence.PHASE_BOUNDARIES


def test_an_inbound_pause_reaches_the_orchestrator_and_answers_the_run_state(
    sockets, real_scene, recording_orchestrator
) -> None:
    async def main():
        async with sockets.serving(real_scene, recording_orchestrator) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                await sockets.send(ws, "pause")
                return await sockets.recv_until(ws, "run_state")

    message = sockets.run(main)

    assert ("pause", ()) in recording_orchestrator.calls
    assert recording_orchestrator.state is RunState.PAUSED
    assert message["text"] == RunState.PAUSED.value  # frontend/main.js reads .text
    assert message["data"]["state"] == RunState.PAUSED.value


def test_one_operators_pause_is_seen_by_every_other_watcher(
    sockets, real_scene, recording_orchestrator
) -> None:
    """Gate A 10.1 again, on the control channel: a second operator watching a run that
    someone else just paused must not be left believing it is still running."""

    async def main():
        async with sockets.serving(real_scene, recording_orchestrator) as server:
            async with sockets.client(server) as acting, sockets.client(server) as watching:
                await sockets.handshake(acting)
                await sockets.handshake(watching)
                await sockets.send(acting, "pause")
                return await sockets.recv_until(watching, "run_state")

    message = sockets.run(main)

    assert message["text"] == RunState.PAUSED.value


def test_closing_the_server_frees_the_port_and_unsubscribes_from_the_scene(
    sockets, fake_scene
) -> None:
    """A live view that is closed and reopened — the normal case over a long session —
    must not leave a listener on ``scene`` or a socket on the port. A leaked subscription
    is a slow memory leak that also keeps translating events for a transport nobody is
    reading; a held port is a server that cannot be restarted."""

    async def main():
        async with sockets.serving(fake_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
            port = server.port
            assert fake_scene._listeners != []
        return port

    port = sockets.run(main)

    assert fake_scene._listeners == []

    probe = socketlib.socket(socketlib.AF_INET, socketlib.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))  # raises OSError if the server still holds it
    finally:
        probe.close()


def test_closing_the_server_stops_the_bridge_translating_scene_events(
    sockets, fake_scene, make_snapshot
) -> None:
    """The other half of the same guarantee, observed rather than inferred: after close,
    a scene change must produce nothing at all."""
    fake_scene.set_objects(make_snapshot("a"))

    async def main():
        async with sockets.serving(fake_scene) as server:
            return server

    server = sockets.run(main)
    server.bridge.pending()  # drain whatever the session produced

    fake_scene.publish(SceneChangeEvent(kind=ChangeKind.OBJECTS_ADDED, object_ids=("a",)))

    assert server.bridge.pending() == ()


def test_a_queued_message_wakes_the_registered_notifier(fake_scene, make_snapshot) -> None:
    """The seam that makes the socket possible at all: ``scene.apply`` is synchronous and
    runs on whatever thread called it, while the transport lives on an event loop. The
    bridge tells the transport *that* there is work; the transport collects it with
    ``pending()``. Without this, an outbound message sits in the queue until some
    unrelated inbound client message happens to flush it — which is exactly why the
    socket had never carried a scene change."""
    bridge = ViewerBridge(fake_scene)
    bridge.attach()
    wakes: list[int] = []
    bridge.set_notifier(lambda: wakes.append(1))

    fake_scene.set_objects(make_snapshot("a"))
    fake_scene.publish(SceneChangeEvent(kind=ChangeKind.OBJECTS_ADDED, object_ids=("a",)))

    assert wakes != []
    assert bridge.pending() != ()


def test_a_raising_notifier_cannot_break_scene_apply(real_scene, add_cube_op) -> None:
    """A transport that has just died must not take ``scene.apply`` with it. Same
    guarantee as the hostile-queue test in ``bridge_test.py``, one layer further out."""
    bridge = ViewerBridge(real_scene)
    bridge.attach()
    bridge.set_notifier(lambda: (_ for _ in ()).throw(RuntimeError("transport gone")))

    result = real_scene.apply(add_cube_op("op1", "a"))

    assert result.ok is True
    assert real_scene.document.head == 1
