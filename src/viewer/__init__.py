"""``viewer`` — the Python half of the live view (ADR-011).

Subscribes to ``scene``'s change events and translates them into the frozen WebSocket
wire protocol (``src/contracts/wire.py``); routes inbound client control messages to
``scene``/``orchestration``. ``scene`` never imports this package — the dependency arrow
points one way, which is what lets the viewer crash, be disabled, or be rebuilt without
touching the geometry core (``contracts.SceneChangeEvent``'s own docstring).

Barrel: re-exports only. See ``README.md`` for the full public interface and
``CLAUDE.md`` for status and local conventions.
"""

from __future__ import annotations

from .bridge import ViewerBridge
from .payloads import snapshot_to_payload, transform_payload
from .server import ViewerTransportUnavailable, serve

__all__ = [
    "ViewerBridge",
    "snapshot_to_payload",
    "transform_payload",
    "serve",
    "ViewerTransportUnavailable",
]
