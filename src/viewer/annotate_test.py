"""The operator's pointing, words, crop and priority marks reaching the rest of the system.

Its own file rather than more cases in ``client_test.py``: routing a message is one
responsibility and turning a selection into measured facts is another, and this feature adds
the second. Same split as the source (``annotate.py`` beside ``client.py``).
"""

from __future__ import annotations

from contracts import ClientMessage, ClientMessageType, ServerMessageType

from viewer import ViewerBridge


def _bridge(scene, orchestrator=None, add_cube_op=None) -> ViewerBridge:
    """A bridge over a scene with one real object in it, so facts have something to
    measure. ``real_scene`` starts empty."""
    if add_cube_op is not None:
        scene.apply(add_cube_op("op1", "box"))
        scene.apply(add_cube_op("op2", "other"))
    return ViewerBridge(scene, orchestrator)


def _annotate(**data) -> ClientMessage:
    return ClientMessage(type=ClientMessageType.ANNOTATE, data=data)


def _set_focus(*object_ids) -> ClientMessage:
    return ClientMessage(type=ClientMessageType.SET_FOCUS, data={"object_ids": list(object_ids)})


# ─── an annotation reaches the agent ────────────────────────────────────────────────


def test_an_annotation_reaches_the_orchestrator(real_scene, recording_orchestrator, add_cube_op) -> None:
    """The whole point of the feature. Before it, a selection arriving from the browser was
    discarded by a handler whose docstring said selection was "presentation state with nothing
    for the server to enforce or record" — so pointing at something reached nothing."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    bridge.handle_client(_annotate(object_ids=["box"], text="too shallow"))

    calls = [c for c in recording_orchestrator.calls if c[0] == "add_annotation"]
    assert len(calls) == 1
    assert calls[0][1][0].text == "too shallow"
    assert calls[0][1][0].object_ids == ("box",)


def test_an_annotation_carries_what_the_object_measured_when_it_was_pointed_at(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Q-02 chose "everything already measured", and the facts are gathered **here**, at the
    moment of pointing, rather than when the agent later reads them. The operator is
    describing what they were looking at; by the time the agent acts, the object may have
    changed, and facts gathered then would describe something the operator never saw."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    bridge.handle_client(_annotate(object_ids=["box"]))

    annotation = recording_orchestrator.calls[-1][1][0]
    assert annotation.facts, "the agent was told an object id and nothing about it"
    assert "box" in annotation.facts[0]


def test_an_unreadable_object_does_not_sink_the_annotation(real_scene, recording_orchestrator, add_cube_op) -> None:
    """An operator can point at something that has just been deleted. Losing the whole
    annotation over one stale id would throw away what they typed — at exactly the moment they
    were trying to tell the agent something was wrong."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    bridge.handle_client(_annotate(object_ids=["box", "no_such_object"], text="this one"))

    annotation = recording_orchestrator.calls[-1][1][0]
    assert annotation.text == "this one"
    assert len(annotation.facts) == 2, "an unreadable object dropped its line silently"


def test_an_annotation_image_is_kept_out_of_the_report_and_fetched_by_id(real_scene, recording_orchestrator, add_cube_op) -> None:
    """``ActionReport`` is text; an image cannot ride it (Q-03). So the annotation says one is
    waiting and names an id, and the picture itself is held for the tool that returns it.
    Putting a megabyte of base64 into a report would cost the agent its whole context."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    bridge.handle_client(_annotate(object_ids=["box"], image="data:image/png;base64,iVBORw0KGgo="))

    annotation = recording_orchestrator.calls[-1][1][0]
    assert annotation.has_image is True
    assert annotation.annotation_id
    assert "base64" not in annotation.render()
    assert bridge.annotation_image(annotation.annotation_id).startswith("data:image/png")


def test_the_operators_words_are_echoed_to_every_watcher(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Gate A 10.1 chose many watchers on one session, and ``_handle_redirect`` already does
    this for typed redirects. An instruction one person gives that the others never see makes
    the build look like it changed its own mind."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    produced = bridge.handle_client(_annotate(object_ids=["box"], text="too shallow"))

    logs = [m for m in produced if m.type is ServerMessageType.LOG]
    assert len(logs) == 1
    assert logs[0].data.get("role") == "operator"
    assert "too shallow" in logs[0].text


def test_pointing_with_nothing_typed_still_says_something_watchers_can_read(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Q-04's click is a complete gesture. An echo naming no object and carrying no text would
    appear in everyone else's transcript as a blank line."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    logs = [
        m
        for m in bridge.handle_client(_annotate(object_ids=["box"]))
        if m.type is ServerMessageType.LOG
    ]
    assert "box" in logs[0].text


def test_a_malformed_annotation_becomes_an_error_message_not_an_exception(real_scene, recording_orchestrator, add_cube_op) -> None:
    """``handle_client``'s standing contract: a bad payload must never take down the loop
    calling it. An empty annotation is refused by ``AnnotatePayload`` itself, and that refusal
    has to arrive as a message the operator can read."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    produced = bridge.handle_client(_annotate())

    assert [m.type for m in produced] == [ServerMessageType.ERROR]
    assert not [c for c in recording_orchestrator.calls if c[0] == "add_annotation"]


def test_an_annotation_with_no_orchestrator_attached_errors_rather_than_raising(
    real_scene, add_cube_op
) -> None:
    """A read-only viewer with no control channel is a legitimate configuration — the same
    guarantee pause/resume/redirect already give."""
    bridge = _bridge(real_scene, None, add_cube_op)

    produced = bridge.handle_client(_annotate(object_ids=["box"]))

    assert [m.type for m in produced] == [ServerMessageType.ERROR]


# ─── focus ──────────────────────────────────────────────────────────────────────────


def test_setting_focus_reaches_the_orchestrator(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Without this the mark is browser decoration: it looks like it worked and the agent is
    never told anything."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    bridge.handle_client(_set_focus("box", "other"))

    assert ("set_focus", (("box", "other"),)) in [
        (c[0], c[1]) for c in recording_orchestrator.calls
    ]


def test_focus_is_echoed_so_a_second_watcher_sees_the_same_marks(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Same reason as the redirect echo, plus one specific to focus: it is standing state, so a
    watcher who cannot see it has no way to discover what the agent is being told every turn."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    produced = bridge.handle_client(_set_focus("box"))

    focus = [m for m in produced if m.type is ServerMessageType.FOCUS]
    assert len(focus) == 1
    assert focus[0].object_ids == ("box",)


def test_clearing_focus_is_echoed_too(real_scene, recording_orchestrator, add_cube_op) -> None:
    """The empty set is the clear (Q-11). An echo suppressed because it is empty would leave
    every other watcher still showing marks that are gone."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    produced = bridge.handle_client(_set_focus())

    assert [m.object_ids for m in produced if m.type is ServerMessageType.FOCUS] == [()]


def test_a_reconnecting_watcher_is_told_what_is_focused(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Focus outlives a page refresh, because it lives on the orchestrator. A greeting that
    omitted it would show a reconnecting operator an unmarked scene while the agent went on
    being told those parts matter — the two disagreeing with no way to notice."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)
    bridge.handle_client(_set_focus("box"))

    greeting = bridge.greeting()

    focus = [m for m in greeting if m.type is ServerMessageType.FOCUS]
    assert len(focus) == 1
    assert focus[0].object_ids == ("box",)


def test_a_greeting_with_nothing_focused_does_not_send_an_empty_focus_message(real_scene, recording_orchestrator, add_cube_op) -> None:
    """The common case is an autonomous run nobody has marked anything in. A message per
    connection saying "nothing is focused" is noise in the action log on every reconnect."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    assert not [m for m in bridge.greeting() if m.type is ServerMessageType.FOCUS]


# ─── an edit made with the handles ──────────────────────────────────────────────────


def _edit(kind: str, **params):
    return ClientMessage(
        type=ClientMessageType.ANNOTATE,
        data={"object_ids": [params.get("object_id", "")], "edit": {"kind": kind, "params": params}},
    )


def test_an_edit_made_with_the_handles_actually_applies(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Without this the edit tools are decoration: the browser sends a well-formed message,
    the socket accepts it, and nothing anywhere changes — the exact shape of failure this
    feature's gate exists to catch."""
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    bridge.handle_client(_edit("move_object", object_id="box", translation=[1.0, 0.0, 0.0]))

    applied = [c for c in recording_orchestrator.calls if c[0] == "apply_operator_edit"]
    assert len(applied) == 1
    assert applied[0][1][0].kind == "move_object"


def test_a_refused_edit_tells_the_operator_why(real_scene, recording_orchestrator, add_cube_op) -> None:
    """Q-21 chose "let me, then tell me what broke". An edit that failed silently would leave
    the operator watching a part snap back with nothing saying why."""
    recording_orchestrator.next_edit_fails = "no object named 'box'"
    bridge = _bridge(real_scene, recording_orchestrator, add_cube_op)

    produced = bridge.handle_client(_edit("move_object", object_id="box", translation=[1.0, 0, 0]))

    logs = [m for m in produced if m.type is ServerMessageType.LOG]
    assert any("no object named" in m.text for m in logs)


def test_an_edit_to_a_backend_that_cannot_do_it_says_so(real_scene, add_cube_op) -> None:
    """An older backend, or a viewer attached read-only. Saying so beats raising, which would
    lose the whole message including any words the operator typed with it."""
    from viewer import ViewerBridge

    class OldOrchestrator:
        def add_annotation(self, _a): pass
        def set_focus(self, _ids): pass

    real_scene.apply(add_cube_op("op1", "box"))
    bridge = ViewerBridge(real_scene, OldOrchestrator())

    produced = bridge.handle_client(_edit("move_object", object_id="box", translation=[1.0, 0, 0]))

    assert any(m.type is ServerMessageType.ERROR for m in produced)
