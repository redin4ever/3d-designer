"""Tests for the two export tools reaching a real handler (ADR-014, Gate B 4.1).

``export_scene`` and ``check_export_budget`` were registered MCP tools with no handler
behind them for the whole build. ``dispatch`` wrapped any handler-less mutating tool into
an ``Operation`` and routed it through the operation log, which requires the kind to be a
registered operation — export never was, so the live call raised
``KeyError: "unknown operation kind 'export_scene'"``. Export is the terminal step of every
journey and the concrete artifact the user defined "it worked" as; it had never once worked
through the agent's own path.
"""

from __future__ import annotations

import json

import pytest
from contracts import Phase, PhaseViolation, RuleError, ToolRole, Vec3
from mcp_server import build_registry, dispatch


@pytest.fixture
def polish_scene(orchestrator, fake_scene):
    """A session in POLISH with one real object — EXPORT is only legal there
    (``contracts.PHASE_ROLES``)."""
    fake_scene.document.phase = Phase.POLISH
    fake_scene.engine.create_primitive("box1", "cube", Vec3(1.0, 1.0, 1.0))
    return fake_scene


# --------------------------------------------------------------------- it is wired

def test_both_export_tools_carry_a_handler(tmp_path) -> None:
    """``src/app/app_test.py``'s "every registered tool has a handler" assertion carved
    these two names out with no comment, which is how a tool an agent can see but nothing
    can execute survived a green suite, a green gate and two QA rounds. When that
    carve-out is removed this is what has to be true."""
    registry = build_registry()
    exported = {spec.name: spec for spec in registry[ToolRole.EXPORT]}
    assert set(exported) == {"export_scene", "check_export_budget"}
    for name, spec in exported.items():
        assert spec.handler is not None, f"{name} is registered with nothing behind it"
        assert callable(spec.handler)


def test_export_scene_through_dispatch_writes_the_file_and_returns_a_banner(
    orchestrator, polish_scene, tmp_path,
) -> None:
    """The terminal step of every journey. If this raises, the user's own definition of
    "it worked" — a file they can open in Roblox — is unreachable through the only
    interface an agent has."""
    lease = orchestrator.acquire(holder="exporter", phase=Phase.POLISH)
    path = str(tmp_path / "out.glb")

    result = dispatch(
        "export_scene",
        {"object_ids": ["box1"], "path": path, "profile_name": "roblox"},
        role=ToolRole.EXPORT, orchestrator=orchestrator, lease=lease,
    )

    assert result["ok"] is True
    assert result["path"] == path
    assert result["profile"] == "roblox"
    assert result["banner"], "no banner — the one signal a person can act on"
    assert path in result["banner"]
    json.dumps(result)  # must be real JSON, not merely dict-shaped
    assert polish_scene.engine.calls, "the engine was never asked to export anything"
    assert any(call[0] == "export_gltf" for call in polish_scene.engine.calls)


def test_export_does_not_appear_in_the_operation_log(
    orchestrator, polish_scene, tmp_path,
) -> None:
    """ADR-014: an export produces no geometry, so a log entry for it is one undo could
    only treat as a no-op — and undoing "an export" would silently roll back the geometry
    operation before it instead."""
    lease = orchestrator.acquire(holder="exporter", phase=Phase.POLISH)
    head_before = polish_scene.document.head

    dispatch(
        "export_scene", {"object_ids": ["box1"], "path": str(tmp_path / "out.glb")},
        role=ToolRole.EXPORT, orchestrator=orchestrator, lease=lease,
    )

    assert polish_scene.document.head == head_before


def test_check_export_budget_answers_without_touching_the_scene(
    orchestrator, polish_scene,
) -> None:
    """It is a read-only question, and it must stay one: a budget check that appended to
    the operation log would put an entry in the undo history for a question nobody asked
    the model to answer.

    It still needs the lease. ``orchestration.authorize`` grants a lease-less caller
    ``INSPECT`` and nothing else — deliberately narrower than "any read-only tool" — so an
    agent that wants budget numbers without the lock uses the INSPECT tools instead. That
    is that module's decision (ADR-013) and this one defers to it rather than keeping a
    second, looser rule of its own."""
    lease = orchestrator.acquire(holder="exporter", phase=Phase.POLISH)
    head_before = polish_scene.document.head

    result = dispatch(
        "check_export_budget", {"object_ids": ["box1"], "profile_name": "roblox"},
        role=ToolRole.EXPORT, orchestrator=orchestrator, lease=lease,
    )

    assert result["total_triangles"] > 0
    assert result["profile"] == "roblox"
    assert result["banner"]
    assert polish_scene.document.head == head_before
    json.dumps(result)


def test_check_export_budget_reports_an_overage_rather_than_refusing(
    orchestrator, polish_scene,
) -> None:
    """Gate A 6.3, verbatim: report, never block. A budget question that raises instead of
    answering leaves the agent with no number to decimate against."""
    lease = orchestrator.acquire(holder="exporter", phase=Phase.POLISH)
    result = dispatch(
        "check_export_budget",
        {"object_ids": ["box1"], "profile_name": "roblox", "asset_class": "background_prop"},
        role=ToolRole.EXPORT, orchestrator=orchestrator, lease=lease,
    )
    assert result["budget"] is not None
    assert result["over_budget_by"] >= 0


def test_an_unknown_profile_name_is_refused_by_name_not_by_traceback(
    orchestrator, polish_scene, tmp_path,
) -> None:
    """``profile_for`` raises a bare ``KeyError`` on an unknown profile. Reaching the agent
    as a traceback, that is exactly the opaque error Gate A 4.2 asked about — it retries
    the same call rather than picking a profile that exists, so the refusal has to carry
    the four names that do."""
    lease = orchestrator.acquire(holder="exporter", phase=Phase.POLISH)
    with pytest.raises(RuleError) as excinfo:
        dispatch(
            "export_scene",
            {"object_ids": ["box1"], "path": str(tmp_path / "o.glb"), "profile_name": "sketchfab"},
            role=ToolRole.EXPORT, orchestrator=orchestrator, lease=lease,
        )
    assert "roblox" in str(excinfo.value)


# --------------------------------------------------------------- it is phase-gated

def test_export_is_refused_before_polish_and_says_how_to_get_there(
    orchestrator, write_lease,
) -> None:
    """EXPORT is legal only in POLISH (``contracts.PHASE_ROLES``). An agent refused with no
    route forward loops on the same call, and since ADR-012 removed the promotion override
    there is no escape hatch to fall back on — the refusal has to teach."""
    with pytest.raises(PhaseViolation) as excinfo:
        dispatch(
            "export_scene", {"object_ids": ["box1"], "path": "out.glb"},
            role=ToolRole.EXPORT, orchestrator=orchestrator, lease=write_lease,
        )
    message = str(excinfo.value)
    assert "polish" in message
    assert "promote_phase" in message


def test_the_read_only_budget_check_is_phase_gated_too(orchestrator) -> None:
    """Read-only does not mean role-free. A budget answer in ``blockout`` is a number about
    geometry nobody has refined yet, and acting on it wastes the whole detail pass."""
    with pytest.raises(PhaseViolation):
        dispatch(
            "check_export_budget", {"object_ids": ["box1"]},
            role=ToolRole.EXPORT, orchestrator=orchestrator, lease=None,
        )
