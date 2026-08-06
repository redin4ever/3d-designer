"""The five wire types the browser implements and the backend never built.

``frontend/src/main.js`` has full handlers for ``HIGHLIGHT``, ``LOG``, ``PROBLEMS``,
``CONFLICT``, ``EXPORT_REPORT`` and ``RUN_STATE``. Before this file, ``translate.py``
constructed five of the protocol's thirteen types and none of those six — so "the latest
change is highlighted" (Gate A 5.3) showed nothing during a real session and the action
log carried connection status and nothing else.

The cause was structural, not a missing branch: a ``SceneChangeEvent`` says *what*
geometry moved and cannot say why, what it broke, or what it fixed. That content only
exists one layer up, in ``ActionReport``. These tests fix the shape of the path for it.

That a real client actually receives each of them is proved separately, over a real
socket, in ``live_messages_test.py`` — queued is not sent.
"""

from __future__ import annotations

from contracts import (
    ActionReport,
    ChangeKind,
    Conflict,
    Defect,
    DefectClass,
    ExportReport,
    Measurement,
    MetricKind,
    Proposal,
    RunState,
    SceneChangeEvent,
    ServerMessageType,
    Severity,
)

from viewer import ViewerBridge


def _defect(object_id: str = "railing", detail: str = "clips the tread by 12mm") -> Defect:
    return Defect(
        defect_class=DefectClass.PART_CLIPPING,
        severity=Severity.BLOCKER,
        object_id=object_id,
        detail=detail,
        magnitude=0.012,
    )


def _types(messages) -> list[ServerMessageType]:
    return [m.type for m in messages]


def _first(messages, message_type: ServerMessageType):
    for message in messages:
        if message.type is message_type:
            return message
    raise AssertionError(f"no {message_type} in {_types(messages)}")


# --------------------------------------------------------------------------------------
# HIGHLIGHT and LOG straight off the scene event — no caller above scene required
# --------------------------------------------------------------------------------------


def test_a_scene_change_highlights_exactly_what_it_touched(real_scene, add_cube_op) -> None:
    """Gate A 5.3, "what just changed, so the operator can find it without hunting".
    ``scene.apply`` has always populated ``SceneChangeEvent.highlight``; nothing read it,
    so the headline feature of the live view was dead on the wire while looking fully
    implemented on both sides of it."""
    bridge = ViewerBridge(real_scene)
    bridge.attach()

    real_scene.apply(add_cube_op("op1", "wall_a"))

    messages = bridge.pending()
    highlight = _first(messages, ServerMessageType.HIGHLIGHT)
    assert highlight.object_ids == ("wall_a",)


def test_the_highlight_arrives_after_the_geometry_it_points_at(real_scene, add_cube_op) -> None:
    """``frontend``'s ``applyHighlight`` looks each id up in the node map it already
    holds. A highlight that arrives before the mesh that created the node silently marks
    nothing, which is indistinguishable from the feature being off."""
    bridge = ViewerBridge(real_scene)
    bridge.attach()

    real_scene.apply(add_cube_op("op1", "wall_a"))

    kinds = _types(bridge.pending())
    assert kinds.index(ServerMessageType.MESH_UPSERT) < kinds.index(ServerMessageType.HIGHLIGHT)


def test_an_event_with_nothing_to_highlight_sends_no_highlight(fake_scene, make_snapshot) -> None:
    """A ``HIGHLIGHT`` with no ids clears the previous one — sending it on every event
    would erase the last real highlight moments after it appeared."""
    fake_scene.set_objects(make_snapshot("a"))
    bridge = ViewerBridge(fake_scene)
    bridge.attach()

    fake_scene.publish(SceneChangeEvent(kind=ChangeKind.OBJECTS_ADDED, object_ids=("a",)))

    assert ServerMessageType.HIGHLIGHT not in _types(bridge.pending())


def test_a_rebuild_that_could_not_complete_reaches_the_action_log(fake_scene) -> None:
    """``scene.history`` fills ``log_line`` only when a rebuild was incomplete or restored
    from a snapshot — precisely the case an operator must not miss. Nothing read that
    field either."""
    bridge = ViewerBridge(fake_scene)
    bridge.attach()

    fake_scene.publish(
        SceneChangeEvent(kind=ChangeKind.ROLLBACK, log_line="replay stopped at op3: handler missing")
    )

    log = _first(bridge.pending(), ServerMessageType.LOG)
    assert log.text == "replay stopped at op3: handler missing"


# --------------------------------------------------------------------------------------
# report_action — the ActionReport path
# --------------------------------------------------------------------------------------


def test_report_action_logs_the_action_line(fake_scene) -> None:
    """The action log's entire content. Before this it carried connection status only, so
    an operator watching a build saw a scene changing for no stated reason."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(
        ActionReport(op_id="op7", ok=True, summary="add_railing applied", changed=("rail_a",))
    )

    log = _first(bridge.pending(), ServerMessageType.LOG)
    assert "op7" in log.text
    assert "add_railing applied" in log.text
    assert log.data["ok"] is True
    assert log.data["changed"] == ["rail_a"]


def test_report_action_logs_why_a_failure_failed(fake_scene) -> None:
    """Gate A 4.2: the agent is told which rule broke. The human watching gets the same
    line, or the viewport just stops changing with no explanation on screen."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(
        ActionReport(
            op_id="op8",
            ok=False,
            summary="add_railing failed",
            error_rule="ops.unsupported_span",
            error_detail="span 12m exceeds 6m",
        )
    )

    log = _first(bridge.pending(), ServerMessageType.LOG)
    assert "ops.unsupported_span" in log.text
    assert "span 12m exceeds 6m" in log.text
    assert log.data["ok"] is False


def test_report_action_highlights_what_changed(fake_scene) -> None:
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(
        ActionReport(op_id="op9", ok=True, summary="applied", changed=("a", "b"))
    )

    assert _first(bridge.pending(), ServerMessageType.HIGHLIGHT).object_ids == ("a", "b")


def test_report_action_does_not_repeat_the_highlight_the_scene_event_already_sent(
    real_scene, add_cube_op
) -> None:
    """``Orchestrator.perform`` calls ``scene.apply`` and *then* reports. Both name the
    same objects, so a naive implementation sends two identical highlights per operation
    — one wasted frame per action at the exact moment the viewport is busiest."""
    bridge = ViewerBridge(real_scene)
    bridge.attach()
    real_scene.apply(add_cube_op("op1", "wall_a"))

    bridge.report_action(
        ActionReport(op_id="op1", ok=True, summary="add_cube applied", changed=("wall_a",))
    )

    assert _types(bridge.pending()).count(ServerMessageType.HIGHLIGHT) == 1


def test_report_action_sends_new_and_resolved_problems(fake_scene) -> None:
    """Gate A 4.1 chose "what changed + key measurements + new problems". The agent gets
    them in its report; without this the operator watching the same run does not."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(
        ActionReport(
            op_id="op10",
            ok=True,
            summary="repair applied",
            changed=("railing",),
            new_problems=(_defect(),),
            resolved_problems=(_defect("tread", "hole closed"),),
        )
    )

    problems = _first(bridge.pending(), ServerMessageType.PROBLEMS)
    assert len(problems.data["new"]) == 1
    assert len(problems.data["resolved"]) == 1
    assert problems.data["new"][0]["object_id"] == "railing"
    assert problems.data["new"][0]["severity"] == Severity.BLOCKER.value
    assert "clips the tread" in problems.text


def test_report_action_stays_quiet_when_there_is_nothing_to_report(fake_scene) -> None:
    """A ``PROBLEMS`` message on every clean action is one log line per operation saying
    nothing, and the channel stops being read by the time it matters."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(ActionReport(op_id="op11", ok=True, summary="applied", changed=("a",)))

    assert ServerMessageType.PROBLEMS not in _types(bridge.pending())


def test_report_action_says_when_checks_were_skipped(fake_scene) -> None:
    """``ActionReport.checks_skipped``'s own docstring: a report with no problems and
    ``checks_skipped=True`` is not a clean bill of health and must never be presented as
    one. Silence on this channel reads as "checked, clean"."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(
        ActionReport(op_id="op12", ok=True, summary="applied", changed=("a",), checks_skipped=True)
    )

    problems = _first(bridge.pending(), ServerMessageType.PROBLEMS)
    assert problems.data["checks_skipped"] is True
    assert "skipped" in problems.text.lower()


def test_report_action_carries_the_measurements_and_assumptions(fake_scene) -> None:
    """Gate B 1.4: an agent that can see what was assumed on its behalf can correct it.
    The operator watching needs the same — a value the tool supplied is exactly the kind
    of thing a human spots as wrong and an agent does not."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(
        ActionReport(
            op_id="op13",
            ok=True,
            summary="add_railing applied",
            changed=("rail",),
            measurements=(
                Measurement(kind=MetricKind.GAP_WIDTH, value=0.004, unit="m", subject="rail|post"),
            ),
            assumptions=("post cross-section defaulted to 5cm x 5cm",),
        )
    )

    log = _first(bridge.pending(), ServerMessageType.LOG)
    assert log.data["measurements"] == ["rail|post gap_width: 0.004m"]
    assert "5cm x 5cm" in log.text


def test_report_action_never_raises_into_its_caller(fake_scene) -> None:
    """``Orchestrator.perform`` is the single path every mutation takes. A viewer that
    raises there fails the operation that already succeeded — the exact inversion the
    whole one-way dependency exists to prevent."""

    class HostileQueue(list):
        def append(self, item) -> None:
            raise RuntimeError("simulated dead transport")

    bridge = ViewerBridge(fake_scene)
    bridge._queue = HostileQueue()

    bridge.report_action(ActionReport(op_id="op14", ok=True, summary="applied", changed=("a",)))


def test_report_action_survives_a_malformed_report(fake_scene) -> None:
    bridge = ViewerBridge(fake_scene)

    bridge.report_action(object())  # type: ignore[arg-type]

    assert bridge.pending() == ()


# --------------------------------------------------------------------------------------
# run state, export, conflicts
# --------------------------------------------------------------------------------------


def test_report_run_state_reads_the_orchestrator_when_not_told(
    fake_scene, recording_orchestrator
) -> None:
    recording_orchestrator.pause()
    bridge = ViewerBridge(fake_scene, recording_orchestrator)

    bridge.report_run_state()

    (message,) = bridge.pending()
    assert message.type is ServerMessageType.RUN_STATE
    assert message.text == RunState.PAUSED.value
    assert message.data["state"] == RunState.PAUSED.value


def test_run_state_carries_text_because_that_is_what_the_browser_reads(fake_scene) -> None:
    """``frontend/src/main.js`` renders ``run state → ${message.text}``. A ``RUN_STATE``
    carrying the value in ``data`` only renders "run state → undefined"."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_run_state(RunState.BLOCKED)

    (message,) = bridge.pending()
    assert message.text == "blocked"


def test_report_export_carries_the_warning_banner(fake_scene) -> None:
    """Gate A 6.3's export warning banner, on the channel
    ``ServerMessageType.EXPORT_REPORT`` was frozen for — kept out of ``PROBLEMS`` because
    it is about a file that was written, not about the live scene."""
    bridge = ViewerBridge(fake_scene)

    bridge.report_export(
        ExportReport(
            path="out/house.glb",
            profile="roblox",
            ok=True,
            triangle_count=21000,
            budget=20000,
            over_budget_by=1000,
            defects=(_defect(),),
        )
    )

    (message,) = bridge.pending()
    assert message.type is ServerMessageType.EXPORT_REPORT
    assert "out/house.glb" in message.text
    assert "1000 over" in message.text
    assert message.data["over_budget_by"] == 1000
    assert message.data["profile"] == "roblox"


def test_report_conflicts_sends_the_geometry_the_operator_has_to_look_at(fake_scene) -> None:
    """Gate A 10.3: surfaced with the exact geometry involved, like a merge conflict, and
    never resolved silently. A conflict message naming no objects leaves the operator with
    a clash and nowhere to look."""
    bridge = ViewerBridge(fake_scene)
    conflict = Conflict(
        conflict_id="c1",
        proposals=(
            Proposal(proposal_id="p1", author="agent-a", target_objects=("wall",), operation_kind="move"),
            Proposal(proposal_id="p2", author="agent-b", target_objects=("wall",), operation_kind="attach"),
        ),
        overlapping_objects=("wall",),
        detail="both touch wall",
    )

    bridge.report_conflicts(conflict)

    (message,) = bridge.pending()
    assert message.type is ServerMessageType.CONFLICT
    assert message.object_ids == ("wall",)
    assert "agent-a" in message.text and "agent-b" in message.text
    assert message.data["conflict_id"] == "c1"


def test_the_same_conflict_is_not_announced_twice(fake_scene) -> None:
    """Conflict detection re-runs on every proposal submission and returns the whole live
    set each time. Re-announcing an unresolved one on every call buries the new one."""
    bridge = ViewerBridge(fake_scene)
    conflict = Conflict(
        conflict_id="c1",
        proposals=(
            Proposal(proposal_id="p1", author="a", target_objects=("wall",), operation_kind="move"),
            Proposal(proposal_id="p2", author="b", target_objects=("wall",), operation_kind="attach"),
        ),
        overlapping_objects=("wall",),
        detail="both touch wall",
    )

    bridge.report_conflicts(conflict)
    bridge.pending()
    bridge.report_conflicts(conflict)

    assert bridge.pending() == ()


def test_reporting_an_action_surfaces_conflicts_the_orchestrator_already_knows_about(
    fake_scene,
) -> None:
    """``Orchestrator.find_conflicts()`` is read-only and already computed. Sweeping it on
    the report path is what makes ``CONFLICT`` reachable without ``orchestration`` having
    to learn that a viewer exists — which it must never do (the arrow points one way)."""

    class OrchestratorWithAConflict:
        state = RunState.RUNNING

        def find_conflicts(self):
            return (
                Conflict(
                    conflict_id="c9",
                    proposals=(
                        Proposal(proposal_id="p1", author="a", target_objects=("wall",), operation_kind="move"),
                        Proposal(proposal_id="p2", author="b", target_objects=("wall",), operation_kind="attach"),
                    ),
                    overlapping_objects=("wall",),
                    detail="both touch wall",
                ),
            )

    bridge = ViewerBridge(fake_scene, OrchestratorWithAConflict())

    bridge.report_action(ActionReport(op_id="op15", ok=True, summary="applied"))

    assert ServerMessageType.CONFLICT in _types(bridge.pending())


def test_an_orchestrator_that_cannot_answer_about_conflicts_is_not_an_error(
    fake_scene, recording_orchestrator
) -> None:
    """``recording_orchestrator`` has no ``find_conflicts``; neither does a viewer attached
    read-only with no orchestrator at all. Both are legitimate configurations."""
    bridge = ViewerBridge(fake_scene, recording_orchestrator)

    bridge.report_action(ActionReport(op_id="op16", ok=True, summary="applied"))

    assert ServerMessageType.CONFLICT not in _types(bridge.pending())
