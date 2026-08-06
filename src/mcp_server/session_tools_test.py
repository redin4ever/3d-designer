"""Tests for the four session tools an agent needs to orient itself and finish
(Gate B 3.1, ADR-012, ADR-013).

Before this file, ``ToolRole.INSPECT`` had **zero** tools: there was no way for a connected
agent to ask what phase it was in, what existed in the scene, or to advance a phase. Gate A
4.4 chose a fully autonomous run, and a fully autonomous run against that registry can build
forever and never promote, never export, never finish. These four tools are the missing half
of the many-readers-one-writer model.
"""

from __future__ import annotations

import json

import pytest
from contracts import AcceptanceResult, Phase, RuleError, ToolRole, Vec3
from mcp_server import dispatch, tools_for

_PRIMITIVE = {"object_id": "box1", "kind": "cube", "size": [1, 1, 1]}


def _read(name: str, params: dict, orchestrator) -> dict:
    return dispatch(name, params, role=ToolRole.INSPECT, orchestrator=orchestrator)


# ------------------------------------------------------------------ they are registered

def test_the_inspect_role_is_no_longer_empty() -> None:
    """An agent with no read tools cannot orient itself, cannot verify its own work, and
    cannot decide when it is done — the reader half of ADR-007 simply was not there."""
    names = {spec.name for spec in tools_for(ToolRole.INSPECT)}
    assert {"get_phase", "list_objects", "describe_object"} <= names


def test_promote_phase_is_an_admin_tool() -> None:
    """ADMIN is legal in every phase (``contracts.ALWAYS_LEGAL_ROLES``). Putting promotion
    behind a phase-scoped role would make the phase an agent is stuck in the one thing
    that stops it leaving."""
    names = {spec.name for spec in tools_for(ToolRole.ADMIN)}
    assert "promote_phase" in names
    assert "promote_phase" not in {spec.name for spec in tools_for(ToolRole.INSPECT)}


def test_the_three_read_tools_never_mutate() -> None:
    """Many INSPECT agents run concurrently precisely because none of their tools can
    mutate. One mutating tool here breaks the guarantee the multi-agent design rests on."""
    for spec in tools_for(ToolRole.INSPECT):
        assert spec.mutating is False, spec.name


# ------------------------------------------------------------------------- get_phase

def test_get_phase_reports_the_phase_and_what_is_legal_in_it(orchestrator) -> None:
    """An agent that cannot ask what phase it is in has to guess, and a guess that is
    wrong costs it a refused call per tool until it finds one that works."""
    result = _read("get_phase", {}, orchestrator)

    assert result["phase"] == "blockout"
    assert "blockout" in result["roles_legal_now"]
    assert "inspect" in result["roles_legal_now"]
    assert "polish" not in result["roles_legal_now"]
    assert "add_primitive" in result["tools_callable_now"]
    json.dumps(result)


def test_get_phase_lists_the_acceptance_queries_and_which_ones_fail(orchestrator) -> None:
    """ADR-012 removed the promotion override, so a failing query is the only thing between
    an unattended agent and a phase it cannot leave. If it cannot see which query fails, it
    has nothing to work from and the run stalls with nobody watching."""
    result = _read("get_phase", {}, orchestrator)

    assert result["can_promote"] is False, "a fresh scene has produced nothing yet"
    assert result["acceptance"], "no acceptance queries reported at all"
    assert result["failing"], "can_promote is false but nothing is listed as failing"
    for failure in result["failing"]:
        assert set(failure) >= {
            "query_id", "subject", "actual", "expected", "suggested_operation", "describe",
        }


def test_a_failing_query_carries_its_subject_value_threshold_and_the_fix(
    orchestrator, monkeypatch,
) -> None:
    """The four fields are what make a refusal actionable rather than a dead end. This
    pins that they survive the trip out to the agent — a renderer that drops
    ``suggested_operation`` turns a fixable failure into an unexplained one."""
    rich = AcceptanceResult(
        query_id="blockout.no_holes",
        passed=False,
        actual=3.0,
        expected=0.0,
        subject="wall_n",
        reason="3 boundary holes remain",
        suggested_operation="fill_boundary_holes(object_id='wall_n')",
    )
    monkeypatch.setattr(orchestrator, "can_promote", lambda: (False, (rich,)))

    failure = _read("get_phase", {}, orchestrator)["failing"][0]

    assert failure["subject"] == "wall_n"
    assert failure["actual"] == 3.0
    assert failure["expected"] == 0.0
    assert failure["suggested_operation"] == "fill_boundary_holes(object_id='wall_n')"


# ----------------------------------------------------------------------- list_objects

def test_list_objects_summarises_each_object(orchestrator, fake_scene) -> None:
    """"What exists in the scene" is the first question any agent asks after a crash, a
    handover, or a resumed session, and it had no answer."""
    fake_scene.engine.create_primitive("box1", "cube", Vec3(2.0, 1.0, 3.0))

    result = _read("list_objects", {}, orchestrator)

    assert result["total"] == 1
    entry = result["objects"][0]
    assert entry["object_id"] == "box1"
    assert entry["triangles"] > 0
    assert entry["dimensions"] == pytest.approx([2.0, 1.0, 3.0])


def test_list_objects_stays_bounded_at_thousands_of_objects(orchestrator, fake_scene) -> None:
    """ADR-011's stated scale is a full game district. A tool that returns every object
    costs more tokens than the agent's whole context at that size, so the one call it
    needs most is the one it can never afford to make."""
    for i in range(2000):
        fake_scene.engine.create_primitive(f"obj{i:04d}", "cube", Vec3(1.0, 1.0, 1.0))

    result = _read("list_objects", {}, orchestrator)

    assert result["total"] == 2000
    assert len(result["objects"]) <= 100, "returned an unbounded list"
    assert result["truncated"] is True
    assert result["next_offset"] == len(result["objects"])
    assert result["hint"], "truncated with no way to ask for the rest"
    assert len(json.dumps(result)) < 40_000


def test_list_objects_pages_through_the_scene(orchestrator, fake_scene) -> None:
    """Truncation without paging is data loss with a nicer name."""
    for i in range(12):
        fake_scene.engine.create_primitive(f"obj{i:02d}", "cube", Vec3(1.0, 1.0, 1.0))

    first = _read("list_objects", {"limit": 5}, orchestrator)
    second = _read("list_objects", {"limit": 5, "offset": first["next_offset"]}, orchestrator)

    assert [o["object_id"] for o in first["objects"]] == [f"obj{i:02d}" for i in range(5)]
    assert [o["object_id"] for o in second["objects"]] == [f"obj{i:02d}" for i in range(5, 10)]


def test_list_objects_filters_by_prefix(orchestrator, fake_scene) -> None:
    """Paging alone still makes an agent read the whole scene to find one railing. A
    filter is what turns "what exists" into "what exists that I care about"."""
    fake_scene.engine.create_primitive("rail_a", "cube", Vec3(1.0, 1.0, 1.0))
    fake_scene.engine.create_primitive("rail_b", "cube", Vec3(1.0, 1.0, 1.0))
    fake_scene.engine.create_primitive("wall_a", "cube", Vec3(1.0, 1.0, 1.0))

    result = _read("list_objects", {"prefix": "rail_"}, orchestrator)

    assert result["total"] == 2
    assert {o["object_id"] for o in result["objects"]} == {"rail_a", "rail_b"}


# -------------------------------------------------------------------- describe_object

def test_describe_object_returns_the_per_object_detail_a_report_omits(
    orchestrator, fake_scene,
) -> None:
    """``ActionReport.detail_hint`` points here by name: above eight changed objects a
    report summarises and tells the agent to call this. If it does not exist, the
    summarised report is a dead end and Gate B 4.3's token fix costs the agent its
    detail."""
    fake_scene.engine.create_primitive("box1", "cube", Vec3(2.0, 1.0, 3.0))

    result = _read("describe_object", {"object_id": "box1"}, orchestrator)

    assert result["object_id"] == "box1"
    assert result["dimensions"] == pytest.approx([2.0, 1.0, 3.0])
    assert result["triangle_count"] > 0
    assert set(result["transform"]) >= {"translation", "rotation", "scale"}
    assert "defects" in result
    json.dumps(result)


def test_describe_object_on_an_unknown_id_does_not_dump_every_object_id(
    orchestrator, fake_scene,
) -> None:
    """A review found a refusal that inlined all 58 live object ids. At the stated scale
    that message is larger than the answer would have been, and it is produced exactly
    when the agent is already lost. The refusal must name the rule, say how many objects
    exist, and show a sample — never the whole scene."""
    for i in range(60):
        fake_scene.engine.create_primitive(f"obj{i:02d}", "cube", Vec3(1.0, 1.0, 1.0))

    with pytest.raises(RuleError) as excinfo:
        _read("describe_object", {"object_id": "nope"}, orchestrator)

    message = str(excinfo.value)
    assert "nope" in message
    assert "60" in message, "did not say how many objects there are"
    assert sum(f"obj{i:02d}" in message for i in range(60)) <= 8
    assert excinfo.value.suggestion


# --------------------------------------------------------------------- promote_phase

def test_promote_phase_refuses_while_the_acceptance_queries_fail(
    orchestrator, write_lease, fake_scene,
) -> None:
    """A phase completes when its queries pass against live geometry, never when an agent
    says it is finished — agents self-report false success in 13-89% of failures, and a
    second agent reviewing that claim catches it at barely above chance (ADR-012)."""
    with pytest.raises(RuleError) as excinfo:
        dispatch(
            "promote_phase", {}, role=ToolRole.ADMIN,
            orchestrator=orchestrator, lease=write_lease,
        )

    assert fake_scene.document.phase is Phase.BLOCKOUT
    assert "promot" in excinfo.value.rule, f"refused by the wrong rule: {excinfo.value.rule}"
    assert excinfo.value.suggestion, "refused with no next step"


def test_a_refused_promotion_returns_the_failing_queries(
    orchestrator, write_lease, monkeypatch,
) -> None:
    """Same reasoning as ``get_phase``: with no override left, the failing query *is* the
    instruction. A refusal that only says "not yet" leaves an unattended run with nothing
    to do next."""
    rich = AcceptanceResult(
        query_id="blockout.no_holes", passed=False, actual=3.0, expected=0.0,
        subject="wall_n", suggested_operation="fill_boundary_holes(object_id='wall_n')",
    )
    monkeypatch.setattr(orchestrator, "can_promote", lambda: (False, (rich,)))

    with pytest.raises(RuleError) as excinfo:
        dispatch(
            "promote_phase", {}, role=ToolRole.ADMIN,
            orchestrator=orchestrator, lease=write_lease,
        )

    message = str(excinfo.value)
    assert "wall_n" in message
    assert "fill_boundary_holes(object_id='wall_n')" in message


def test_promote_phase_has_no_force_parameter() -> None:
    """ADR-012 deleted the override at Gate B 1.1. Re-introducing it as a tool parameter
    would restore exactly the behaviour that let a phase hand off on an agent's say-so,
    through a door the ADR did not think to close."""
    spec = next(s for s in tools_for(ToolRole.ADMIN) if s.name == "promote_phase")
    assert "force" not in spec.input_schema.get("properties", {})
    assert "force" not in json.dumps(spec.input_schema)


def test_a_force_parameter_is_rejected_rather_than_ignored(orchestrator, write_lease) -> None:
    """Silently ignoring ``force=True`` tells the agent the override worked. It has to be
    refused by name, or an agent will believe it promoted and carry on against a phase it
    never left."""
    with pytest.raises(RuleError) as excinfo:
        dispatch(
            "promote_phase", {"force": True}, role=ToolRole.ADMIN,
            orchestrator=orchestrator, lease=write_lease,
        )
    assert "force" in str(excinfo.value)


def test_promote_phase_advances_once_the_queries_pass(
    orchestrator, write_lease, fake_scene,
) -> None:
    """The gate has to open. An autonomous run that can never reach POLISH can never
    export, and export is the artifact the user defined success as."""
    # Both halves matter: the log entry (what `can_promote` counts as this phase's output)
    # and the geometry itself (what its acceptance query measures). `FakeScene.apply`
    # records the operation without executing a handler, so the object has to be created
    # directly — a real `Scene` would do both from the one call.
    dispatch(
        "add_primitive", _PRIMITIVE, role=ToolRole.BLOCKOUT,
        orchestrator=orchestrator, lease=write_lease,
    )
    fake_scene.engine.create_primitive("box1", "cube", Vec3(1.0, 1.0, 1.0))

    result = dispatch(
        "promote_phase", {}, role=ToolRole.ADMIN,
        orchestrator=orchestrator, lease=write_lease,
    )

    assert result["ok"] is True
    assert result["from"] == "blockout"
    assert result["to"] == "refine"
    assert fake_scene.document.phase is Phase.REFINE


def test_promotion_widens_the_tools_get_phase_reports(
    orchestrator, write_lease, fake_scene,
) -> None:
    """"What can I do now" and "what will actually be accepted" have to be the same answer
    (Gate B 4.4). If ``get_phase`` still reports the old phase's tools after a promotion,
    the agent plans against a catalogue that no longer applies."""
    # Both halves matter: the log entry (what `can_promote` counts as this phase's output)
    # and the geometry itself (what its acceptance query measures). `FakeScene.apply`
    # records the operation without executing a handler, so the object has to be created
    # directly — a real `Scene` would do both from the one call.
    dispatch(
        "add_primitive", _PRIMITIVE, role=ToolRole.BLOCKOUT,
        orchestrator=orchestrator, lease=write_lease,
    )
    fake_scene.engine.create_primitive("box1", "cube", Vec3(1.0, 1.0, 1.0))
    before = _read("get_phase", {}, orchestrator)["tools_callable_now"]

    dispatch(
        "promote_phase", {}, role=ToolRole.ADMIN,
        orchestrator=orchestrator, lease=write_lease,
    )
    after = _read("get_phase", {}, orchestrator)["tools_callable_now"]

    assert "add_railing" not in before
    assert "add_railing" in after
