"""Tests for the import tool declaration reaching MCP registry composition."""

from __future__ import annotations

from contracts import ToolRole
from importing import IMPORT_SPECS
from mcp_server.import_specs import IMPORT_TOOL_SPECS


def test_import_specs_publish_one_handler_less_mutating_tool_for_all_build_phases():
    """Agents must see import in every modelling phase while dispatch routes it to the log."""
    assert IMPORT_TOOL_SPECS == IMPORT_SPECS
    assert len(IMPORT_TOOL_SPECS) == 1
    spec = IMPORT_TOOL_SPECS[0]
    assert spec.name == "import_model_file"
    assert spec.handler is None
    assert spec.mutating is True
    assert spec.roles == (
        ToolRole.BLOCKOUT,
        ToolRole.REFINE,
        ToolRole.DETAIL,
        ToolRole.POLISH,
    )


def test_import_schema_declares_local_file_and_unit_conversion_controls():
    """The MCP schema must expose the safety and coordinate controls an agent can choose."""
    spec = IMPORT_TOOL_SPECS[0]
    schema = spec.input_schema
    assert schema["required"] == ["path"]
    properties = schema["properties"]
    assert properties["source_up"]["enum"] == ["AUTO", "X", "Y", "Z"]
    assert properties["unit_scale"]["type"] == "number"
    assert properties["unit_scale"]["exclusiveMinimum"] == 0
    assert properties["path"]["format"] == "local-path"
