"""``serve()`` stays behind a lazy import so ``src/viewer`` is fully testable with no
``websockets`` installed — this sandbox has neither ``websockets`` nor ``starlette`` on
disk despite both being declared project dependencies (``pyproject.toml``).
"""

from __future__ import annotations

import sys
import types

import pytest

from viewer import ViewerTransportUnavailable, serve


def test_serve_raises_a_named_error_when_websockets_is_not_installed(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "websockets", None)  # forces ImportError on import

    with pytest.raises(ViewerTransportUnavailable, match="websockets"):
        serve(object(), object())


def test_serve_wires_a_fresh_bridge_when_websockets_is_available(monkeypatch, fake_scene) -> None:
    """Simulates the package being installed via ``sys.modules`` injection, so the wiring
    logic — not the real network stack — gets coverage without the dependency present."""
    calls: list[tuple] = []
    sentinel = object()
    fake_module = types.ModuleType("websockets")

    def _fake_serve(handler, host, port):
        calls.append((handler, host, port))
        return sentinel

    fake_module.serve = _fake_serve
    monkeypatch.setitem(sys.modules, "websockets", fake_module)

    result = serve(fake_scene, object(), host="0.0.0.0", port=9999)

    assert result is sentinel
    assert len(calls) == 1
    _, host, port = calls[0]
    assert (host, port) == ("0.0.0.0", 9999)
