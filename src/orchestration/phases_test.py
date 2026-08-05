"""Tests for the phase machine and tool-role partitioning (ADR-007, ADR-003, ADR-005).

A phase hands off when its acceptance queries pass against live geometry, never when an
agent says it is finished (ADR-005) — agents self-report false success in 13-89% of
failures, and a second agent reviewing that claim catches it barely above chance. Every
test here is written against that contract; most fail with ``NotImplementedError`` until
``phases.py`` is implemented (Rule 4), which is expected for this phase.
"""

from __future__ import annotations

import pytest

from contracts import PHASE_ORDER, AcceptanceResult, Phase, ToolRole
from orchestration import Orchestrator


def test_orchestrator_starts_in_blockout_and_promotes_one_phase_at_a_time(scene) -> None:
    """Blockout is deliberately the starting phase — primitives, proportion, placement,
    no detail (``contracts.Phase.BLOCKOUT``'s own docstring). Advancing more than one
    phase per call, or landing somewhere other than the very next entry in
    ``PHASE_ORDER``, would let a run skip refine or detail entirely — exactly the
    "stitched together" failure mode this product exists to prevent, since each later
    pass exists to convert blockout's boxes into something else."""
    orch = Orchestrator(scene)
    assert orch.phase is Phase.BLOCKOUT

    assert orch.promote(force=True) is Phase.REFINE
    assert orch.phase is Phase.REFINE
    assert orch.promote(force=True) is Phase.DETAIL
    assert orch.phase is Phase.DETAIL
    assert orch.promote(force=True) is Phase.POLISH
    assert orch.phase is Phase.POLISH
    assert tuple(PHASE_ORDER) == (Phase.BLOCKOUT, Phase.REFINE, Phase.DETAIL, Phase.POLISH)


def test_can_promote_is_false_with_the_failing_queries_on_a_fresh_scene(scene) -> None:
    """A fresh scene has produced no geometry at all, so real acceptance queries for
    "blockout is complete" cannot pass. ``can_promote`` returning a bare ``False`` with
    no ``AcceptanceResult`` to explain it would leave an agent guessing what to fix —
    Gate A 4.2 requires the agent be told which rule broke, never left to infer it."""
    orch = Orchestrator(scene)

    can, results = orch.can_promote()

    assert can is False
    assert results != ()
    assert all(isinstance(r, AcceptanceResult) for r in results)
    assert any(r.passed is False for r in results)


def test_promote_with_force_overrides_a_failing_check_and_records_it(scene) -> None:
    """Gate A 6.3: the user chose report-over-block, so a forced promotion must succeed
    — but the override has to stay visible afterward, not merely be effective. If it
    were silent, an operator reviewing the run later could not tell a promotion that
    genuinely earned its acceptance queries from one somebody pushed through over a
    known-failing check, which is exactly the distinction a report-over-block policy
    depends on being able to draw."""
    orch = Orchestrator(scene)
    can, _ = orch.can_promote()
    assert can is False, "promoting on a fresh scene needs the override to succeed at all"

    new_phase = orch.promote(force=True)

    assert new_phase is Phase.REFINE
    logged = scene.document().operations
    assert any(
        op.kind == "phase_promotion" and op.params.get("forced") is True
        for op in logged
    ), "the forced override left no trace in the log"


def test_promoting_past_polish_raises(scene) -> None:
    """``POLISH`` is the last entry in ``PHASE_ORDER``; there is nothing to promote to.
    An implementation that let this call succeed would produce a phase value that
    exists nowhere in the professional progression this product models, and every
    downstream consumer of ``Phase`` would have to guard against it forever after."""
    orch = Orchestrator(scene)
    for _ in range(len(PHASE_ORDER) - 1):
        orch.promote(force=True)
    assert orch.phase is Phase.POLISH

    with pytest.raises(ValueError):
        orch.promote(force=True)


def test_tools_for_returns_between_one_and_eight_tools_for_every_role(scene) -> None:
    """Published evidence puts the accuracy-optimal visible tool-set size at roughly
    2-7, with real degradation reported past ~10-15 (``contracts.ToolRole``'s own
    docstring) — an agent choosing from thirty overlapping tool descriptions
    demonstrably invents tool names and borrows argument schemas from the wrong one.
    This bound is load-bearing, not a style preference, so it is asserted explicitly
    for every role rather than spot-checked on one."""
    orch = Orchestrator(scene)

    for role in ToolRole:
        tools = orch.tools_for(role)
        assert 1 <= len(tools) <= 8, f"{role} exposes {len(tools)} tools"


def test_tools_for_inspect_returns_only_non_mutating_tools(scene) -> None:
    """A single mutating tool reaching an INSPECT-role agent breaks the concurrency
    guarantee every other test in this module relies on: many INSPECT agents run
    concurrently *precisely because* none of their tools can mutate (ADR-007). This is
    the one role where the check matters most, so it gets its own explicit assertion
    rather than being folded into the bounds check above."""
    orch = Orchestrator(scene)

    tools = orch.tools_for(ToolRole.INSPECT)

    assert tools != ()
    assert all(t.mutating is False for t in tools)
