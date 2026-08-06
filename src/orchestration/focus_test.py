"""Focus is standing state; an annotation is an event (Q-10, Q-11, A-013).

That distinction is the whole unit, and having it backwards is the failure this file exists to
prevent. A focus set drained on delivery is forgotten by the agent's third action — and the
operator cannot tell, because it worked the first time. An annotation that persists is
re-delivered forever, so the agent keeps acting on an instruction given once.
"""

from __future__ import annotations

from contracts import Operation, OperatorAnnotation, Phase
from orchestration import Orchestrator


def _run(orch, lease, n: int = 1):
    """Perform one geometry operation and return its report."""
    return orch.perform(Operation(op_id=f"op{n}", kind="add_cube", produced_objects=("box",)), lease)


def test_focus_survives_every_report_until_it_is_cleared(scene) -> None:
    """Q-10 chose "a standing instruction it re-reads every turn". If focus were drained like
    an operator note, the agent would be told once and then work on for the rest of the
    session with no idea the operator was watching anything in particular."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.set_focus(("stair_railing_02", "newel_post_01"))

    for n in (1, 2, 3):
        assert _run(orch, lease, n).operator_focus == ("stair_railing_02", "newel_post_01")


def test_setting_focus_replaces_the_whole_set_rather_than_adding_to_it(scene) -> None:
    """The browser sends the complete set every time — ``FocusPayload`` is declarative. If
    this accumulated, unmarking something in the UI would leave it marked on the backend, and
    the two would disagree permanently with the operator's own screen being the wrong one."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)

    orch.set_focus(("a", "b"))
    orch.set_focus(("c",))

    assert _run(orch, lease).operator_focus == ("c",)


def test_an_empty_set_clears_focus(scene) -> None:
    """The only route back from a marked scene to an unmarked one (Q-11). Without it, focus
    could be set and never taken down short of restarting the run."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)

    orch.set_focus(("a",))
    orch.set_focus(())

    assert _run(orch, lease).operator_focus == ()


def test_focus_is_readable_without_performing_an_operation(scene) -> None:
    """An idle run performs nothing, and the operator can still mark parts. Something has to
    answer "what is focused" outside the write path — the MCP tool that hands an agent its
    operator context is exactly that caller, and it runs when nothing is happening."""
    orch = Orchestrator(scene)
    orch.set_focus(("railing",))

    assert orch.focus == ("railing",)


def test_an_annotation_reaches_the_agent_once_and_only_once(scene) -> None:
    """The opposite rule to focus, for the opposite reason. Pointing at something is an event;
    re-delivering it every turn would have the agent acting repeatedly on one remark."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.add_annotation(OperatorAnnotation(object_ids=("tread_04",), text="too shallow"))

    first = _run(orch, lease, 1)
    second = _run(orch, lease, 2)

    assert len(first.operator_annotations) == 1
    assert first.operator_annotations[0].text == "too shallow"
    assert second.operator_annotations == ()


def test_annotations_arrive_in_the_order_they_were_made(scene) -> None:
    """Two remarks about one part read as a correction — "thicker", then "actually, much
    thicker". Delivered out of order they read as the opposite instruction."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.add_annotation(OperatorAnnotation(text="first"))
    orch.add_annotation(OperatorAnnotation(text="second"))

    assert [a.text for a in _run(orch, lease).operator_annotations] == ["first", "second"]


def test_focus_and_annotations_are_independent(scene) -> None:
    """Marking a part important must not consume a remark about it, and vice versa. They
    share an operator and nothing else."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.set_focus(("railing",))
    orch.add_annotation(OperatorAnnotation(text="one off"))

    first = _run(orch, lease, 1)
    second = _run(orch, lease, 2)

    assert first.operator_focus == ("railing",)
    assert len(first.operator_annotations) == 1
    assert second.operator_focus == ("railing",), "focus was drained along with the annotation"
    assert second.operator_annotations == ()


def test_a_run_with_nobody_watching_reports_neither(scene) -> None:
    """The overwhelmingly common case — a fully autonomous run (Gate A 4.4). Neither field may
    cost anything or appear in the rendered report when nobody has touched anything."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)

    report = _run(orch, lease)

    assert report.operator_focus == ()
    assert report.operator_annotations == ()
    assert "FOCUS" not in report.render()
