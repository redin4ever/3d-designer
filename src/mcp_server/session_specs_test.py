"""Orientation responses keep an agent tied to the operator and the next verified step."""

from contracts import Phase
from mcp_server.phase_tools import get_phase


def test_get_phase_returns_focus_visible_tools_and_next_actions(orchestrator) -> None:
    orchestrator.set_focus(("roof", "front_window"))

    result = get_phase(orchestrator=orchestrator)

    assert result["phase"] == Phase.BLOCKOUT.value
    assert result["operator_focus"] == ["roof", "front_window"]
    assert {"get_phase", "add_primitive", "describe_object"} <= set(result["focused_tools"])
    assert result["next_actions"]
    assert any("measure" in action.lower() or "inspect" in action.lower() for action in result["next_actions"])


def test_get_phase_names_promotion_when_acceptance_passes(orchestrator) -> None:
    result = get_phase(orchestrator=orchestrator)

    if result["can_promote"]:
        assert any("promote_phase" in action for action in result["next_actions"])
