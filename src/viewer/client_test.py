"""Routing ``contracts.ClientMessage`` actions through ``ViewerBridge.handle_client``.

Each test proves the *route*, not the destination module's own behaviour — ``scene`` and
``orchestration`` each have their own suite for that. What matters here is that the right
call, with the right argument, happens at all — the wire protocol's only job at this
boundary.
"""

from __future__ import annotations

from contracts import CheckCadence, ClientMessage, ClientMessageType, RunState, ServerMessageType

from viewer import ViewerBridge


def test_handle_client_pause_calls_through_and_reports_the_new_run_state(
    fake_scene, recording_orchestrator
) -> None:
    bridge = ViewerBridge(fake_scene, recording_orchestrator)

    (message,) = bridge.handle_client(ClientMessage(type=ClientMessageType.PAUSE))

    assert ("pause", ()) in recording_orchestrator.calls
    assert message.type is ServerMessageType.RUN_STATE
    assert message.data["state"] == RunState.PAUSED.value


def test_handle_client_resume_restores_the_running_state(fake_scene, recording_orchestrator) -> None:
    bridge = ViewerBridge(fake_scene, recording_orchestrator)
    bridge.handle_client(ClientMessage(type=ClientMessageType.PAUSE))

    (message,) = bridge.handle_client(ClientMessage(type=ClientMessageType.RESUME))

    assert ("resume", ()) in recording_orchestrator.calls
    assert message.data["state"] == RunState.RUNNING.value


def test_handle_client_rollback_with_steps_reaches_scene_undo(fake_scene) -> None:
    bridge = ViewerBridge(fake_scene)

    bridge.handle_client(ClientMessage(type=ClientMessageType.ROLLBACK, data={"steps": 3}))

    assert ("undo", (3,)) in fake_scene.calls


def test_handle_client_rollback_with_checkpoint_reaches_scene_rollback_to(fake_scene) -> None:
    bridge = ViewerBridge(fake_scene)

    bridge.handle_client(
        ClientMessage(type=ClientMessageType.ROLLBACK, data={"checkpoint": "before_railings"})
    )

    assert ("rollback_to", ("before_railings",)) in fake_scene.calls


def test_handle_client_rollback_rejects_an_ambiguous_target_without_crashing(fake_scene) -> None:
    """A rollback naming both fields is malformed input, not a server crash —
    ``RollbackTarget.__post_init__`` already rejects it; the bridge must turn that
    rejection into one ``ERROR`` message rather than letting it propagate and take the
    calling loop down with it."""
    bridge = ViewerBridge(fake_scene)

    (message,) = bridge.handle_client(
        ClientMessage(type=ClientMessageType.ROLLBACK, data={"steps": 1, "checkpoint": "x"})
    )

    assert message.type is ServerMessageType.ERROR
    assert fake_scene.calls == []


def test_handle_client_redirect_reaches_orchestrator_add_operator_note(
    fake_scene, recording_orchestrator
) -> None:
    """The only route a mid-run instruction has back to the agent — MCP is call/response,
    so a server cannot push into a connected agent's context uninvited
    (``RedirectPayload``'s own docstring)."""
    bridge = ViewerBridge(fake_scene, recording_orchestrator)

    bridge.handle_client(
        ClientMessage(type=ClientMessageType.REDIRECT, data={"text": "check the north wall"})
    )

    assert recording_orchestrator.notes == ["check the north wall"]


def test_handle_client_set_cadence_reaches_orchestrator_set_cadence(
    fake_scene, recording_orchestrator
) -> None:
    bridge = ViewerBridge(fake_scene, recording_orchestrator)

    bridge.handle_client(
        ClientMessage(type=ClientMessageType.SET_CADENCE, data={"cadence": "phase_boundaries"})
    )

    assert ("set_cadence", (CheckCadence.PHASE_BOUNDARIES,)) in recording_orchestrator.calls


def test_handle_client_pause_without_an_orchestrator_reports_an_error_not_a_crash(fake_scene) -> None:
    bridge = ViewerBridge(fake_scene)  # no orchestrator attached

    (message,) = bridge.handle_client(ClientMessage(type=ClientMessageType.PAUSE))

    assert message.type is ServerMessageType.ERROR


def test_handle_client_request_full_scene_returns_a_full_scene_message(real_scene, add_cube_op) -> None:
    real_scene.apply(add_cube_op("op1", "a"))
    bridge = ViewerBridge(real_scene)

    (message,) = bridge.handle_client(ClientMessage(type=ClientMessageType.REQUEST_FULL_SCENE))

    assert message.type is ServerMessageType.FULL_SCENE
    assert message.object_ids == ("a",)


def test_handle_client_select_is_a_defined_no_op_not_an_error(fake_scene) -> None:
    bridge = ViewerBridge(fake_scene)

    produced = bridge.handle_client(
        ClientMessage(type=ClientMessageType.SELECT, data={"object_id": "a"})
    )

    assert produced == ()


def test_handle_client_with_the_real_orchestrator_pause_resume_round_trips(fake_scene) -> None:
    """Integration sanity against the actual, GREEN ``orchestration.Orchestrator`` — not
    just this package's own recording double — so a signature drift between the two
    modules shows up here rather than only in a full end-to-end run."""
    from orchestration import Orchestrator

    orchestrator = Orchestrator(scene=object())  # pause/resume never touch scene
    bridge = ViewerBridge(fake_scene, orchestrator)

    bridge.handle_client(ClientMessage(type=ClientMessageType.PAUSE))
    assert orchestrator.state is RunState.PAUSED

    bridge.handle_client(ClientMessage(type=ClientMessageType.RESUME))
    assert orchestrator.state is RunState.RUNNING
