"""Tests for the action loop: cadence policy, operator notes, and report assembly
(Gate A 3.1, Gate A 4.1, ADR-005).

Gate A 3.1, verbatim: geometry checks run "after every change that touches geometry with
a settings menu setting that enables me changing that". The default is the strictest
option; the setting exists because the user asked for it, not as an escape hatch — and a
report with skipped checks must never be mistaken for a clean one. Most tests here fail
with ``NotImplementedError`` until ``reporting.py`` is implemented (Rule 4), which is
expected for this phase.
"""

from __future__ import annotations

from contracts import CheckCadence, Operation, Phase
from orchestration import Orchestrator


def test_every_geometry_change_cadence_runs_checks_and_populates_measurements(scene) -> None:
    """This is the default cadence, chosen as the strictest option (Gate A 3.1). A report
    that comes back with no measurements at all after a geometry-producing operation
    gives an agent nothing to verify its own work against — the entire reason ADR-005
    requires a re-run measurement rather than a claim."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    op = Operation(op_id="op1", kind="add_cube", produced_objects=("box",))

    report = orch.perform(op, lease)

    assert report.checks_skipped is False
    assert report.measurements != ()


def test_phase_boundaries_cadence_skips_mid_phase_and_says_so(scene) -> None:
    """Under this cadence, a mid-phase operation should not pay for a measurement pass
    that only needs to run at promotion. But a skipped check must never read as a clean
    result — ``ActionReport.render()``'s own contract — or an agent would treat "nobody
    looked" as "nothing is wrong", which is a materially worse outcome than not checking
    at all."""
    orch = Orchestrator(scene, cadence=CheckCadence.PHASE_BOUNDARIES)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    op = Operation(op_id="op1", kind="add_cube", produced_objects=("box",))

    report = orch.perform(op, lease)

    assert report.checks_skipped is True
    assert "not a clean result" in report.render()


def test_on_request_cadence_skips_unless_explicitly_asked(scene) -> None:
    """The loosest cadence setting — checks run only when a caller asks for them
    separately, never automatically inside ``perform``. Silently running checks anyway
    would defeat the entire point of offering this setting; silently *not* marking the
    report as skipped would reintroduce the false-clean-result failure this field exists
    to prevent."""
    orch = Orchestrator(scene, cadence=CheckCadence.ON_REQUEST)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    op = Operation(op_id="op1", kind="add_cube", produced_objects=("box",))

    report = orch.perform(op, lease)

    assert report.checks_skipped is True
    assert "not a clean result" in report.render()


def test_set_cadence_takes_effect_on_the_very_next_perform_call(scene) -> None:
    """Gate A 3.1 asks for a settings-menu control that changes this mid-run, not a
    value fixed at construction. An implementation that only reads ``cadence`` once in
    ``__init__`` would make ``set_cadence`` a no-op that silently fails to do what its
    name promises."""
    orch = Orchestrator(scene)  # defaults to EVERY_GEOMETRY_CHANGE
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.set_cadence(CheckCadence.PHASE_BOUNDARIES)

    op = Operation(op_id="op1", kind="add_cube", produced_objects=("box",))
    report = orch.perform(op, lease)

    assert report.checks_skipped is True


def test_operator_note_rides_out_on_the_next_report_exactly_once(scene) -> None:
    """MCP is call/response — a server cannot push into a connected agent's context
    uninvited, so a redirect typed into the browser mid-run has exactly one path out:
    the next tool response (``ActionReport.operator_notes``'s own docstring). If the
    note were never cleared, every later report would keep repeating stale guidance,
    which an agent has no way to distinguish from a fresh instruction; if it were
    dropped instead of delivered, the operator's redirect would silently never reach the
    agent at all."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer-a", Phase.BLOCKOUT)
    orch.add_operator_note("make the railing simpler")

    op1 = Operation(op_id="op1", kind="add_cube", produced_objects=("box",))
    report1 = orch.perform(op1, lease)
    op2 = Operation(op_id="op2", kind="add_cube", produced_objects=("box2",))
    report2 = orch.perform(op2, lease)

    assert "make the railing simpler" in report1.operator_notes
    assert report2.operator_notes == ()
