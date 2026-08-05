"""Routing one ``contracts.ClientMessage`` to ``scene``/``orchestration`` and reporting
back what happened.

Mixed into ``ViewerBridge`` (``bridge.py``). Every handler here is the one route its
client action has to the rest of the system — see each method's docstring for which call
it must reach, and why.

Nothing here is implemented yet (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import (
    CadencePayload,
    CheckCadence,
    ClientMessage,
    ClientMessageType,
    RedirectPayload,
    RollbackTarget,
    ServerMessage,
    ServerMessageType,
)

__all__ = ["ClientMixin"]

_HANDLER_NAMES: dict[ClientMessageType, str] = {
    ClientMessageType.PAUSE: "_handle_pause",
    ClientMessageType.RESUME: "_handle_resume",
    ClientMessageType.ROLLBACK: "_handle_rollback",
    ClientMessageType.REDIRECT: "_handle_redirect",
    ClientMessageType.SET_CADENCE: "_handle_set_cadence",
    ClientMessageType.REQUEST_FULL_SCENE: "_handle_request_full_scene",
    ClientMessageType.SELECT: "_handle_select",
}


class ClientMixin:
    """Expects ``self._scene``, ``self._orchestrator``, ``self._enqueue()`` and
    ``self._next_seq()`` — see ``bridge.py``."""

    def handle_client(self, msg: ClientMessage) -> tuple[ServerMessage, ...]:
        """Apply one client action and return exactly the messages it produced.

        Never raises: a malformed payload (e.g. a rollback naming both ``steps`` and
        ``checkpoint`` — ``RollbackTarget.__post_init__`` rejects that) becomes one
        ``ERROR`` message instead of an exception that would take down whatever loop is
        calling this — the same "a broken action must not break the caller" shape
        ``translate.py`` applies to a broken scene listener.
        """
        start = len(self._queue)
        try:
            self._dispatch_client(msg)
        except Exception as exc:
            self._enqueue(
                ServerMessage(
                    type=ServerMessageType.ERROR,
                    seq=self._next_seq(),
                    text=f"{type(exc).__name__}: {exc}",
                )
            )
        produced = tuple(self._queue[start:])
        del self._queue[start:]
        return produced

    def _dispatch_client(self, msg: ClientMessage) -> None:
        name = _HANDLER_NAMES.get(msg.type)
        if name is None:
            self._enqueue(
                ServerMessage(
                    type=ServerMessageType.ERROR,
                    seq=self._next_seq(),
                    text=f"unhandled client message type: {msg.type!r}",
                )
            )
            return
        getattr(self, name)(msg)

    def _ensure_orchestrator(self) -> bool:
        if self._orchestrator is None:
            self._enqueue(
                ServerMessage(
                    type=ServerMessageType.ERROR,
                    seq=self._next_seq(),
                    text="no orchestrator attached — pause/resume/redirect/set_cadence are unavailable",
                )
            )
            return False
        return True

    def _enqueue_run_state(self) -> None:
        state = self._orchestrator.state
        self._enqueue(
            ServerMessage(
                type=ServerMessageType.RUN_STATE,
                seq=self._next_seq(),
                data={"state": state.value},
            )
        )

    def _handle_pause(self, msg: ClientMessage) -> None:
        """PAUSE calls through to ``orchestrator.pause()`` and reports the new run
        state — the only way an operator watching the live view takes the wheel without
        stopping the run outright."""
        if not self._ensure_orchestrator():
            return
        self._orchestrator.pause()
        self._enqueue_run_state()

    def _handle_resume(self, msg: ClientMessage) -> None:
        if not self._ensure_orchestrator():
            return
        self._orchestrator.resume()
        self._enqueue_run_state()

    def _handle_rollback(self, msg: ClientMessage) -> None:
        """Routes to ``scene.undo`` or ``scene.rollback_to`` depending on which of
        ``RollbackTarget``'s two mutually exclusive fields is set."""
        target = RollbackTarget(**msg.data)
        if target.steps is not None:
            self._scene.undo(target.steps)
        else:
            self._scene.rollback_to(target.checkpoint)

    def _handle_redirect(self, msg: ClientMessage) -> None:
        """The only route a mid-run instruction has back to the agent — MCP is
        call/response, so a server cannot push into a connected agent's context
        uninvited (``RedirectPayload``'s own docstring)."""
        if not self._ensure_orchestrator():
            return
        payload = RedirectPayload(**msg.data)
        self._orchestrator.add_operator_note(payload.text)

    def _handle_set_cadence(self, msg: ClientMessage) -> None:
        cadence = msg.data.get("cadence")
        if not isinstance(cadence, CheckCadence):
            cadence = CheckCadence(cadence)
        if not self._ensure_orchestrator():
            return
        payload = CadencePayload(cadence=cadence)
        self._orchestrator.set_cadence(payload.cadence)

    def _handle_request_full_scene(self, msg: ClientMessage) -> None:
        self._enqueue(self._build_full_scene_message())

    def _handle_select(self, msg: ClientMessage) -> None:
        """Selection is presentation state with nothing for the server to enforce or
        record; a defined no-op here rather than an ``ERROR`` for a legitimate message
        type (``contracts.ClientMessageType.SELECT``)."""
        return
