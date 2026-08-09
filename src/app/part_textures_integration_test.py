from __future__ import annotations

import inspect

from app import live
from contracts import MeshPayload
from ops import OPS, OP_SPECS
from mcp_server import tools_for
from contracts import ToolRole
from testing import FakeEngine


def test_texture_tools_are_registered_for_agents_and_replay() -> None:
    names = {spec.name for spec in OP_SPECS}
    expected = {"create_texture_material", "update_texture_material", "apply_texture_material"}
    assert expected <= names
    assert expected <= set(OPS)
    assert "list_texture_materials" in {spec.name for spec in tools_for(ToolRole.INSPECT)}


def test_engine_and_wire_expose_texture_definitions() -> None:
    engine = FakeEngine()
    assert callable(getattr(engine, "create_texture_material", None))
    payload = MeshPayload(object_id="part", positions=[], indices=[])
    assert getattr(payload, "material_definitions", None) == {}


def test_live_server_wires_the_managed_texture_asset_resolver() -> None:
    source = inspect.getsource(live._QuietHandler.do_GET)
    assert "/textures/" in source
    assert "resolve_texture_asset" in source
