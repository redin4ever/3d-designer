"""An operator's own edit, applied while the run is paused (Q-17, Q-19).

Q-17 chose "you have to press Pause first". That answer removes every two-writer race — and
it collides head-on with ``perform``, which refuses while paused. The pause exists to stop
the *agent* writing; a human who pressed Pause in order to make a change is the one caller it
must not stop, and this file is that distinction.
"""

from __future__ import annotations

import pytest

from contracts import Operation, Phase, RunState
from orchestration import Orchestrator


def _move(object_id: str = "box") -> Operation:
    return Operation(
        op_id="edit-1",
        kind="move_object",
        params={"object_id": object_id, "translation": [1.0, 0.0, 0.0]},
        target_objects=(object_id,),
    )


def test_an_operator_edit_applies_while_the_run_is_paused(scene) -> None:
    """The whole feature. Q-17 made pausing the precondition for editing, so an edit that is
    refused *because* the run is paused would mean the manual tools can never work at all."""
    orch = Orchestrator(scene)
    orch.pause()

    report = orch.apply_operator_edit(_move())

    assert report.ok
    assert orch.state is RunState.PAUSED, "applying an edit resumed the build behind the operator"


def test_an_operator_edit_also_works_while_the_run_is_going(scene) -> None:
    """The UI only offers editing while paused, but the backend must not be the thing that
    enforces it — a rule enforced in two places disagrees eventually, and this is the copy
    that would refuse a legitimate call with a confusing reason."""
    orch = Orchestrator(scene)

    assert orch.apply_operator_edit(_move()).ok


def test_an_operator_edit_is_logged_like_any_other_operation(scene) -> None:
    """Q-19 chose one shared history. If a manual edit skipped the log it would be invisible
    to roll-back-N-steps and to replay — the operator's own change would be the one thing
    undo could not reach."""
    orch = Orchestrator(scene)
    orch.pause()

    orch.apply_operator_edit(_move())

    assert scene.document.head == 1, "the edit never reached the operation log"


def test_an_operator_edit_tells_the_agent_what_changed(scene) -> None:
    """Q-18 chose "yes, always". Otherwise the agent is working from a picture of the scene
    that is quietly wrong, and it will undo the operator's fix without ever knowing it
    existed."""
    orch = Orchestrator(scene)
    orch.pause()

    report = orch.apply_operator_edit(_move())

    assert any("operator" in note.lower() for note in report.operator_notes) or report.changed


def test_a_failing_operator_edit_comes_back_as_a_report_not_an_exception(scene) -> None:
    """A refusal has to reach the browser as something the operator can read. An exception
    escaping here would surface as a dropped socket message and a UI that simply did nothing
    — the failure mode Q-21 ("let me, then tell me what broke") is written against.

    Driven by making the scene raise, because the real refusals this guards live down there:
    an unknown operation kind, an object deleted between selecting it and dragging it, a
    degenerate scale. The double accepts anything, so asserting on it would prove nothing."""

    class RefusingScene:
        """Everything ``apply_operator_edit`` touches, with ``apply`` raising."""

        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def apply(self, *_args, **_kwargs):
            raise ValueError("no object named 'box'")

    orch = Orchestrator(RefusingScene(scene))
    orch.pause()

    report = orch.apply_operator_edit(_move())

    assert report.ok is False
    assert "box" in report.error_detail
