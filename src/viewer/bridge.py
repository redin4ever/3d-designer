"""``ViewerBridge`` — the live-scene half of the WebSocket boundary (ADR-011).

Owns the outbound message queue, the bridge's own monotonic ``seq`` counter, and the
``scene``/``orchestrator`` subscription lifecycle. Translating a
``contracts.SceneChangeEvent`` into wire messages lives in ``translate.py``; routing an
inbound ``contracts.ClientMessage`` lives in ``client.py`` — both mixed in here so a
caller sees one class with the full public surface, the same "one file per
responsibility, one class assembled" shape ``scene`` and ``orchestration`` use.

``ViewerBridge.__init__`` is real, already-working code, like ``Scene.__init__`` in
``src/scene/__init__.py`` — it is not a stub (Rule 4's exception for pure composition and
field initialisation).
"""

from __future__ import annotations

from typing import Callable

from contracts import ServerMessage

from .client import ClientMixin
from .translate import TranslateMixin

__all__ = ["ViewerBridge"]


class ViewerBridge(TranslateMixin, ClientMixin):
    """Subscribes to one ``scene`` and optionally routes control messages through one
    ``orchestrator``. See ``README.md`` for the full contract.

    ``scene`` never imports this module — the reverse is fine and is the entire point: a
    broken or absent viewer must never take the geometry core down with it.
    """

    def __init__(self, scene: object, orchestrator: object | None = None) -> None:
        self._scene = scene
        self._orchestrator = orchestrator
        self._unsubscribe: Callable[[], None] | None = None
        self._queue: list[ServerMessage] = []
        self._seq_counter = 0

    def attach(self) -> None:
        """Subscribe to ``scene``. Idempotent — calling it twice does not register a
        second listener, so a reconnect that forgets to ``detach()`` first does not
        leak."""
        if self._unsubscribe is None:
            self._unsubscribe = self._scene.subscribe(self._on_scene_change)

    def detach(self) -> None:
        """Unsubscribe from ``scene``. Safe to call when not attached, and safe to call
        twice — the leaked-subscription failure mode this exists to prevent is a slow
        memory leak across reconnects in a long-running session."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @property
    def seq(self) -> int:
        """The last sequence number this bridge assigned."""
        return self._seq_counter

    def _next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    def _enqueue(self, message: ServerMessage) -> None:
        """Append to the outbound queue, defensively — a queue that raises must not
        propagate into ``scene``'s call stack."""
        try:
            self._queue.append(message)
        except Exception:
            pass

    def pending(self) -> tuple[ServerMessage, ...]:
        """Drain and return every queued outbound message, oldest first."""
        drained = tuple(self._queue)
        self._queue.clear()
        return drained

    def full_scene(self) -> ServerMessage:
        """Every object currently in the engine, as one ``FULL_SCENE`` message. Does not
        touch the outbound queue — this is a pull, for an explicit resync request or the
        first message on a new connection, not a push."""
        return self._build_full_scene_message()
