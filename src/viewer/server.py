"""Lazy WebSocket transport for ``ViewerBridge`` (ADR-011's "incremental live-view
updates over WebSocket").

``websockets`` is a declared project dependency (``pyproject.toml``) but this module must
not fail to import when it is absent — every other test in ``src/viewer`` runs with no
network stack installed at all (ADR-008's "testable in isolation" applies here too). The
import happens only inside :func:`serve`, and only when it is actually called.

Nothing here is implemented yet (Rule 4 — tests come first).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from contracts import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType, WIRE_VERSION

__all__ = ["serve", "ViewerTransportUnavailable"]


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


def _encode(message: ServerMessage) -> str:
    return json.dumps(asdict(message), default=str)


def _decode(raw: str) -> ClientMessage:
    obj = json.loads(raw)
    return ClientMessage(type=ClientMessageType(obj["type"]), data=obj.get("data", {}))


async def _handle_connection(bridge: Any, websocket: Any) -> None:
    """One connection's whole lifecycle: hello, initial full scene, then request/response
    for as long as the socket stays open. Not exercised by this package's own test suite
    (no real ``websockets`` install in this environment — see ``server_test.py``'s module
    docstring); kept intentionally small so the untested surface stays small too.
    """
    await websocket.send(
        _encode(ServerMessage(type=ServerMessageType.HELLO, data={"wire_version": WIRE_VERSION}))
    )
    await websocket.send(_encode(bridge.full_scene()))
    async for raw in websocket:
        for out in bridge.handle_client(_decode(raw)):
            await websocket.send(_encode(out))
        for out in bridge.pending():
            await websocket.send(_encode(out))


def serve(scene: Any, orchestrator: Any, *, host: str = "127.0.0.1", port: int = 8766) -> object:
    """Start (but do not run) a WebSocket server wired to a fresh ``ViewerBridge``.

    Lazily imports ``websockets``, raising :class:`ViewerTransportUnavailable` if it is
    missing, then returns the ``websockets.serve(...)`` awaitable/context-manager — the
    caller owns the event loop (``asyncio.run`` or an already-running one), not this
    function, so it stays usable from a synchronous composition root or an async one
    alike.
    """
    try:
        import websockets
    except ImportError as exc:
        raise ViewerTransportUnavailable("websockets") from exc

    from .bridge import ViewerBridge

    bridge = ViewerBridge(scene, orchestrator)
    bridge.attach()

    async def _handler(websocket: Any) -> None:
        await _handle_connection(bridge, websocket)

    return websockets.serve(_handler, host, port)
