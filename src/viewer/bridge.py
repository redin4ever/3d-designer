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

from contracts import WIRE_VERSION, ServerMessage, ServerMessageType

from .annotate import AnnotateMixin
from .client import ClientMixin
from .report import ReportMixin
from .translate import TranslateMixin

TRANSCRIPT_HISTORY = 200
"""How many conversation lines a reconnecting client is handed. Matches the frontend
transcript's own cap: replaying more than it will keep is work thrown away."""

__all__ = ["ViewerBridge"]


class ViewerBridge(TranslateMixin, ClientMixin, AnnotateMixin, ReportMixin):
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
        self._notifier: Callable[[], None] | None = None
        self._last_highlight: tuple[str, ...] = ()
        self._seen_conflicts: set[str] = set()
        self._transcript: list[ServerMessage] = []
        # Annotation images, held out of the report and out of the transcript. See annotate.py.
        self._images: dict[str, str] = {}
        self._annotation_seq = 0

    def set_notifier(self, notifier: Callable[[], None] | None) -> None:
        """Register a zero-argument callback fired whenever a message is queued.

        Deliberately a *wake-up*, not a delivery: the callback is told there is work and
        collects it with :meth:`pending`, so the queue stays the single place an outbound
        message lives. A sink that received the message directly would double-send
        everything ``handle_client`` already returns to its own caller, and would have to
        be re-entrant with ``scene``'s synchronous ``_emit`` — which runs on whatever
        thread called ``scene.apply``, never the event loop's.
        """
        self._notifier = notifier

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
        """Append to the outbound queue and wake whoever is draining it.

        Both halves are defensive, and independently so: a queue that raises must not
        propagate into ``scene``'s call stack, and neither must a transport whose loop has
        already closed underneath it. ``scene.apply`` completing correctly is not allowed
        to depend on anything about the browser.
        """
        if message.type is ServerMessageType.LOG:
            self._remember(message)
        try:
            self._queue.append(message)
        except Exception:
            return
        notifier = self._notifier
        if notifier is None:
            return
        try:
            notifier()
        except Exception:
            pass

    def pending(self) -> tuple[ServerMessage, ...]:
        """Drain and return every queued outbound message, oldest first."""
        drained = tuple(self._queue)
        self._queue.clear()
        return drained

    def full_scene(self) -> ServerMessage:
        """Every object currently in the engine, as one ``FULL_SCENE`` message. Does not
        touch the outbound queue — this is a pull, for an explicit resync request, not a
        push."""
        return self._build_full_scene_message()

    def _remember(self, message: ServerMessage) -> None:
        """Keep a bounded history of the conversation, so a refresh does not erase it.

        The transcript lived only in the browser, so reloading the page — or opening it in
        a second window — showed an empty conversation while the run carried on. Nothing
        was lost on the backend; there was simply no way to ask for it. This is that.

        Bounded, because a long build is thousands of operations and a session that
        remembered all of them would hold the whole run in memory and hand every new
        watcher a wall of text. The cap matches the frontend transcript's own.

        In memory and per-process on purpose: this is session history, not scene history.
        The scene itself persists in the operation log; a restarted server genuinely has
        nothing to say about a conversation that happened before it existed, and pretending
        otherwise would mean writing chat to disk that no one asked to keep.
        """
        self._transcript.append(message)
        if len(self._transcript) > TRANSCRIPT_HISTORY:
            del self._transcript[: len(self._transcript) - TRANSCRIPT_HISTORY]

    def greeting(self) -> tuple[ServerMessage, ...]:
        """Everything a freshly-connected client needs before the first change arrives.

        Run state first, then ``HELLO``, then the scene — and every one of them carries
        the sequence number already reached rather than taking new ones. That is what
        makes a second watcher connecting free for the first (Gate A 10.1): a greeting
        that consumed three numbers would put every already-connected client one gap past
        its baseline, and ``frontend``'s seq rule turns a gap into a full resync of the
        whole scene. Ordering ``RUN_STATE`` *before* ``HELLO`` is the other half of the
        same arithmetic — ``HELLO`` and ``FULL_SCENE`` reset the client's baseline to
        their own seq, so a same-numbered ``RUN_STATE`` sent after them would be dropped
        as a duplicate and a run paused before anyone connected would display as running.
        """
        seq = self._seq_counter
        messages: list[ServerMessage] = []
        run_state = self._run_state_message(seq=seq)
        if run_state is not None:
            messages.append(run_state)
        messages.append(
            ServerMessage(
                type=ServerMessageType.HELLO,
                seq=seq,
                data={
                    "wire_version": WIRE_VERSION,
                    "scene_id": getattr(getattr(self._scene, "document", None), "scene_id", ""),
                },
            )
        )
        messages.append(self._build_full_scene_message(seq=seq))

        # The conversation so far, after the scene, replayed at the same `seq` as
        # everything else in the greeting for the reason above: consuming numbers here
        # would push every already-connected watcher past its baseline and trigger a full
        # resync in each of them, just because somebody opened a second tab.
        messages.extend(
            ServerMessage(
                type=ServerMessageType.LOG,
                seq=seq,
                text=past.text,
                data={**past.data, "replayed": True},
            )
            for past in self._transcript
        )
        return tuple(messages)
