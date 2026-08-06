"""The live WebSocket transport: one server, many watchers, one ``ViewerBridge``.

``websockets`` is a declared project dependency (``pyproject.toml``) and **is** installed
here, but the import still happens inside :func:`require_websockets` rather than at module
scope. The reason is not availability, it is blast radius: ``viewer`` is imported by
``app``'s composition root on every startup including headless ones, and every other test
in this package runs with no socket, no event loop and no network stack touched at all
(ADR-008's "testable in isolation"). Hoisting the import would make a transport failure a
startup failure for a product that is explicitly allowed to run with the live view off.

Nothing here is implemented yet (Rule 4 — tests come first).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import asdict
from typing import Any

from contracts import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType, WIRE_VERSION

__all__ = ["serve", "ViewerSocketServer", "ViewerTransportUnavailable", "encode", "decode"]


class ViewerTransportUnavailable(RuntimeError):
    """``serve()`` was called but the ``websockets`` package is not installed.

    Named rather than a bare ``ImportError`` so a caller can catch exactly this and
    decide to run headless (tests, CI, a session with no browser attached) instead of the
    whole process dying on import of a module nobody asked to run yet.
    """

    def __init__(self, package: str) -> None:
        super().__init__(
            f"viewer.serve() needs the {package!r} package, which is not installed. "
            f"Install it (`pip install {package}`) or run without a live view — nothing "
            "else in src/viewer needs it."
        )
        self.package = package


def require_websockets() -> Any:
    """Import ``websockets`` now, or raise :class:`ViewerTransportUnavailable`."""
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise ViewerTransportUnavailable("websockets") from exc
    return websockets


def encode(message: ServerMessage) -> str:
    return json.dumps(asdict(message), default=str)


def decode(raw: str | bytes) -> ClientMessage:
    obj = json.loads(raw)
    return ClientMessage(type=ClientMessageType(obj["type"]), data=obj.get("data", {}))


#: Produced by one client's action but relevant to every watcher (Gate A 10.1). One
#: operator pausing the run while another watches must not leave the second one believing
#: it is still running.
BROADCAST_TO_OTHERS = frozenset(
    {ServerMessageType.RUN_STATE, ServerMessageType.PHASE, ServerMessageType.LOG}
)
#: ``LOG`` is here for the operator's own echoed instruction. A message typed by one watcher
#: that the others never see makes the build look like it changed its own mind — and the
#: sender needs it too, as the confirmation that the backend actually has their words.


class ViewerSocketServer:
    """One listening socket, one :class:`~viewer.ViewerBridge`, any number of clients.

    Owns three things the bridge deliberately does not: the set of live connections, the
    task that drains the bridge's queue onto them, and the bind/close lifecycle.
    """

    def __init__(self, bridge: Any, *, host: str = "127.0.0.1", port: int = 8766) -> None:
        self.bridge = bridge
        self.host = host
        self.requested_port = port
        self._clients: set[Any] = set()
        self._server: Any = None
        self._loop: Any = None
        self._wake: Any = None
        self._flusher: Any = None

    @property
    def port(self) -> int:
        """The port actually bound. Differs from ``requested_port`` when that was ``0``."""
        if self._server is None:
            return self.requested_port
        for sock in self._server.sockets:
            return int(sock.getsockname()[1])
        return self.requested_port

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self) -> "ViewerSocketServer":
        """Bind, subscribe to the scene, and start draining the bridge onto the wire.

        Subscribing here rather than in :func:`serve` keeps ``attach``/``detach`` paired
        with ``start``/``close``: a composition root that builds a server and then decides
        to stay headless leaves no listener behind on ``scene``.
        """
        websockets = require_websockets()
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self.bridge.set_notifier(self._notify)
        self.bridge.attach()
        self._server = await websockets.serve(self._handle, self.host, self.requested_port)
        self._flusher = asyncio.create_task(self._flush_loop())
        return self

    async def close(self) -> None:
        """Unsubscribe, stop draining, close every connection, free the port. Idempotent."""
        self.bridge.set_notifier(None)
        self.bridge.detach()
        if self._flusher is not None:
            self._flusher.cancel()
            with suppress(asyncio.CancelledError):
                await self._flusher
            self._flusher = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._clients.clear()
        self._loop = None
        self._wake = None

    async def serve_forever(self) -> None:
        """Run until cancelled. The shape a composition root's ``forge3d serve`` wants."""
        if self._server is None:
            await self.start()
        await self._server.serve_forever()

    async def broadcast(self, message: ServerMessage, *, exclude: Any = None) -> None:
        """Send to every connection, dropping any that fails.

        One watcher's dead socket must not stop the fanout: without the per-client
        ``except`` a half-open TCP connection — the normal result of a closed laptop lid —
        aborts the loop partway and leaves every client after it in iteration order
        silently stale, which is the failure the whole protocol's seq rules exist to make
        impossible.
        """
        if not self._clients:
            return
        payload = encode(message)
        for client in tuple(self._clients):
            if client is exclude:
                continue
            try:
                await client.send(payload)
            except Exception:  # noqa: BLE001 — one dead client, not a dead server
                self._clients.discard(client)

    def _notify(self) -> None:
        """The bridge's wake-up, called synchronously on whatever thread ran
        ``scene.apply`` — which is never the event loop's. ``call_soon_threadsafe`` is the
        only safe hand-off, and it is correct from the loop thread too."""
        loop, wake = self._loop, self._wake
        if loop is None or wake is None:
            return
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:
            pass  # loop already closed — the transport is gone, the scene is not

    async def _flush_loop(self) -> None:
        """Drain the bridge's queue onto every client, forever.

        The event is cleared *before* draining, never after: a message queued during the
        drain then re-sets it and is picked up next time round, whereas clearing
        afterwards would swallow exactly that message — the last change of a build, lost
        because it arrived at the wrong microsecond.
        """
        while True:
            await self._wake.wait()
            self._wake.clear()
            for message in self.bridge.pending():
                await self.broadcast(message)

    async def _handle(self, websocket: Any) -> None:
        """One connection's whole lifecycle."""
        self._clients.add(websocket)
        try:
            for message in self.bridge.greeting():
                await websocket.send(encode(message))
            async for raw in websocket:
                await self._handle_inbound(websocket, raw)
        except Exception:  # noqa: BLE001 — a dropped connection is not a server error
            pass
        finally:
            self._clients.discard(websocket)

    async def _handle_inbound(self, websocket: Any, raw: str | bytes) -> None:
        """Route one client message and answer it.

        The answer goes to the client that asked — a resync is that client's business —
        except for the types in :data:`BROADCAST_TO_OTHERS`, which are facts about the run
        rather than replies to a request.
        """
        try:
            inbound = decode(raw)
        except Exception:  # noqa: BLE001
            await websocket.send(
                encode(
                    ServerMessage(
                        type=ServerMessageType.ERROR,
                        seq=self.bridge.seq,
                        text="unparseable client message",
                    )
                )
            )
            return
        for out in self.bridge.handle_client(inbound):
            await websocket.send(encode(out))
            if out.type in BROADCAST_TO_OTHERS:
                await self.broadcast(out, exclude=websocket)

    async def __aenter__(self) -> "ViewerSocketServer":
        return await self.start()

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()


def serve(
    scene: Any,
    orchestrator: Any = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
) -> ViewerSocketServer:
    """Build (but do not bind) a live-view server wired to a fresh ``ViewerBridge``.

    Fails fast with :class:`ViewerTransportUnavailable` here rather than at the first
    ``await``, so a composition root can decide to run headless at wiring time.

    The caller owns the event loop: ``async with viewer.serve(scene, orch) as s: await
    s.serve_forever()``. ``host`` stays loopback by default and must not be widened
    (A-005, ADR-009 — every connected agent has arbitrary code execution by explicit user
    choice, and nothing about that is safe to expose off-host).
    """
    require_websockets()

    from .bridge import ViewerBridge

    return ViewerSocketServer(ViewerBridge(scene, orchestrator), host=host, port=port)
