"""Tests for run control — pause, resume, and run state (Gate A 5.4).

The build runs fully autonomously; pause and resume exist so a human watching can take
the wheel without stopping it by default. Pause is cooperative: checked between
operations, never mid-operation, so the log is never left half-applied
(``contracts.RunState.PAUSED``'s own docstring). Most tests here fail with
``NotImplementedError`` until ``run.py`` and ``reporting.py`` are implemented (Rule 4),
which is expected for this phase.
"""

from __future__ import annotations

import pytest

from contracts import Operation, Phase, RunState
from orchestration import Orchestrator, RunPaused


def test_pause_sets_run_state_to_paused(scene) -> None:
    """``state`` is the one signal a viewer or a supervising process can poll to show
    "the operator hit pause" without guessing from the absence of new reports."""
    orch = Orchestrator(scene)

    orch.pause()

    assert orch.state is RunState.PAUSED


def test_perform_while_paused_raises_and_applies_nothing(scene) -> None:
    """This module's chosen answer to "raises or defers": **raises**, checked before
    ``self._scene.apply`` runs. Pause is cooperative and checked between operations, not
    mid-operation — so a call made while paused must be refused whole, never partially
    applied and never silently queued for later (MCP is call/response; there is no later
    moment to deliver a deferred result into once this call has already returned)."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.pause()

    op = Operation(op_id="op1", kind="add_cube", target_objects=("box",))
    with pytest.raises(RunPaused):
        orch.perform(op, lease)

    assert scene.document().head == 0, "a paused run must not have applied the operation"


def test_resume_restores_running_state(scene) -> None:
    """A pause with no way back would make the control a kill switch rather than the
    "take the wheel, then hand it back" control Gate A 5.4 asked for."""
    orch = Orchestrator(scene)
    orch.pause()

    orch.resume()

    assert orch.state is RunState.RUNNING
