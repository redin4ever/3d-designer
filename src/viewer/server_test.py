"""``serve()``'s wiring and the JSON codec, with no socket bound and no event loop.

The real transport is exercised end to end in ``live_socket_test.py``. What is left here
is everything that must hold *before* anything is bound: the named-error path when
``websockets`` is missing, the loopback default, and that what goes on the wire is the
shape ``frontend/src/socket.js`` parses. These stay separate because they are the cases a
machine with no network stack still has to be able to check (ADR-008).
"""

from __future__ import annotations

import json
import sys

import pytest

from contracts import ClientMessageType, ServerMessage, ServerMessageType

from viewer import ViewerSocketServer, ViewerTransportUnavailable, serve
from viewer.server import decode, encode


def test_serve_raises_a_named_error_when_websockets_is_not_installed(monkeypatch) -> None:
    """Raised at wiring time rather than at the first ``await``, so a composition root can
    fall back to headless before it has an event loop — ``app.build_app`` catches exactly
    this and continues without a live view."""
    monkeypatch.setitem(sys.modules, "websockets", None)  # forces ImportError on import

    with pytest.raises(ViewerTransportUnavailable, match="websockets"):
        serve(object())


def test_serve_wires_a_fresh_bridge_to_the_given_scene(fake_scene, recording_orchestrator) -> None:
    server = serve(fake_scene, recording_orchestrator, port=9999)

    assert isinstance(server, ViewerSocketServer)
    assert server.bridge._scene is fake_scene
    assert server.bridge._orchestrator is recording_orchestrator
    assert server.requested_port == 9999


def test_serve_does_not_subscribe_until_it_is_started(fake_scene) -> None:
    """``start``/``close`` are the pair that owns the subscription. Subscribing in
    ``serve()`` would leak a listener for every server that is built and never run — and a
    composition root that decides to stay headless does exactly that."""
    serve(fake_scene)

    assert fake_scene._listeners == []


def test_serve_binds_loopback_by_default(fake_scene) -> None:
    """A-005/ADR-009: every connected agent has arbitrary code execution by explicit user
    choice. Defaulting that bind to anything but loopback hands it to the network."""
    server = serve(fake_scene)

    assert server.host == "127.0.0.1"
    assert server.requested_port == 8766


def test_encode_produces_the_flat_json_the_browser_parses() -> None:
    """``frontend`` was built in parallel against ``contracts.wire`` alone. A disagreement
    about field names or nesting surfaces only at live WebSocket runtime otherwise, which
    is the worst place to find it (``RollbackTarget``'s own docstring)."""
    raw = encode(ServerMessage(type=ServerMessageType.LOG, seq=7, text="add_cube applied"))
    obj = json.loads(raw)

    assert obj["type"] == "log"
    assert obj["seq"] == 7
    assert obj["text"] == "add_cube applied"
    assert obj["object_ids"] == []


def test_decode_reads_the_client_message_shape_frontend_sends() -> None:
    message = decode(json.dumps({"type": "set_cadence", "data": {"cadence": "on_request"}}))

    assert message.type is ClientMessageType.SET_CADENCE
    assert message.data == {"cadence": "on_request"}
