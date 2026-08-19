"""Deterministic workflow evals for the context an MCP agent actually receives."""

from contracts import PHASE_ORDER, Phase, ToolRole
from mcp_server.registry import focused_tools


def _names(phase: Phase, focus: ToolRole | None = None) -> set[str]:
    return {spec.name for spec in focused_tools(phase, focus)}


def test_default_workflow_catalogues_are_compact_and_phase_relevant() -> None:
    for phase in PHASE_ORDER:
        names = _names(phase)
        assert len(names) < 30, (phase, len(names))
        assert {"get_phase", "get_operator_context", "list_objects", "describe_object"} <= names
        assert "raw_execute" not in names

    assert "add_primitive" in _names(Phase.BLOCKOUT)
    assert "add_railing" in _names(Phase.REFINE)
    assert "apply_edge_treatment" in _names(Phase.DETAIL)
    assert "export_scene" in _names(Phase.POLISH, ToolRole.EXPORT)


def test_each_specialist_focus_keeps_its_complete_semantic_role() -> None:
    cases = (
        (Phase.REFINE, ToolRole.REPAIR),
        (Phase.REFINE, ToolRole.ALIGN),
        (Phase.DETAIL, ToolRole.DETAIL),
        (Phase.POLISH, ToolRole.POLISH),
        (Phase.POLISH, ToolRole.EXPORT),
    )
    for phase, role in cases:
        names = _names(phase, role)
        assert names
        assert "get_phase" in names
        assert "raw_execute" not in names
