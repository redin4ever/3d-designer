"""Tests for the SDK 2.0 bridge — the layer that turns this module's registry and
``dispatch`` into something the installed ``mcp`` SDK can actually serve (ADR-003).

This is the file that closes the gap the previous pass filed rather than hid: the
transports were wired against the SDK's **1.x** low-level decorator API
(``Server.list_tools()`` / ``Server.call_tool()``), which 2.0.0 removed. Verified against
the installed package rather than from memory: ``mcp.server.lowlevel.Server`` in 2.0.0 has
neither attribute, and takes ``on_list_tools`` / ``on_call_tool`` **constructor callbacks**
instead. That seam is the right one here for a reason worth stating — the alternative,
``mcp.server.MCPServer.add_tool``, derives each tool's JSON Schema by introspecting a
Python signature, and every :class:`contracts.ToolSpec` in this product already carries a
hand-written schema with enums, ``exclusiveMinimum`` and ``additionalProperties: False``
that no signature can express. The callback seam hands our schema through untouched.

The guarantee these tests hold is not "the SDK works". It is that *this* module's rules
survive the trip through it: every tool is declared, with its role; a read-only call takes
no write lease; a mutating call takes one; and a refusal arrives as a **result** naming a
rule and a next step (Gate A 4.2), never as an exception that becomes a stack trace three
frames inside someone else's package.
"""

from __future__ import annotations

import json

import pytest
from contracts import Phase, ToolRole

from mcp_server import sdk_bridge

pytest.importorskip("mcp.server.lowlevel", reason="the MCP SDK is not installed here")


@pytest.fixture
def sdk():
    return sdk_bridge.load_sdk("test")


@pytest.fixture
def specs():
    return sdk_bridge.tool_specs()


def _text(result) -> str:
    return "\n".join(block.text for block in result.content if getattr(block, "text", None))


# ------------------------------------------------------------------ the catalogue

def test_every_registered_tool_is_declared_to_the_client(sdk, specs) -> None:
    """A tool absent from ``tools/list`` does not exist as far as any client is concerned.
    The registry deliberately refuses to cap or hide anything (Gate B 3.3); a bridge that
    quietly dropped tools would reinstate the exact defect ``_cap.py`` was deleted for."""
    declared = {tool.name for tool in sdk_bridge.sdk_tools(sdk, specs.values())}
    assert declared == set(specs)
    assert {"get_phase", "add_primitive", "export_scene", "raw_execute"} <= declared


def test_each_declared_tool_carries_its_roles_and_its_own_json_schema(sdk, specs) -> None:
    """Two things a connected agent cannot work out for itself. The role is how it knows
    which phase a tool belongs to *before* being refused; the hand-written schema is the
    only thing that says ``kind`` is one of six strings rather than any string at all —
    the difference between a rejected call and a wasted round trip."""
    by_name = {tool.name: tool for tool in sdk_bridge.sdk_tools(sdk, specs.values())}

    add_primitive = by_name["add_primitive"]
    assert add_primitive.meta is not None, "no _meta — the client cannot see the role"
    assert add_primitive.meta["roles"] == [ToolRole.BLOCKOUT.value]
    assert add_primitive.meta["mutating"] is True
    assert add_primitive.input_schema == specs["add_primitive"].input_schema
    assert add_primitive.input_schema["properties"]["kind"]["enum"]
    assert add_primitive.description

    get_phase = by_name["get_phase"]
    assert get_phase.meta["roles"] == [ToolRole.INSPECT.value]
    assert get_phase.meta["mutating"] is False
    assert get_phase.annotations is not None
    assert get_phase.annotations.read_only_hint is True


def test_the_declared_catalogue_survives_json(sdk, specs) -> None:
    """It travels the wire as JSON. A schema holding a dataclass, an enum member or a NaN
    serialises here and fails at the client, which is the worst place to find out."""
    for tool in sdk_bridge.sdk_tools(sdk, specs.values()):
        json.dumps(tool.model_dump(by_alias=True, exclude_none=True))


def test_default_discovery_is_phase_focused_and_omits_raw(orchestrator) -> None:
    """A fresh blockout session should not ask the model to choose among the whole
    cross-phase catalogue. It gets construction plus the small verification core, while
    later-phase and unrestricted tools remain out of normal discovery."""
    visible = sdk_bridge.focused_tool_specs(orchestrator)

    assert {"set_tool_focus", "get_phase", "list_objects", "describe_object"} <= set(visible)
    assert {"add_primitive", "add_wall"} <= set(visible)
    assert "add_railing" not in visible
    assert "export_scene" not in visible
    assert "raw_execute" not in visible
    assert len(visible) < 30


def test_raw_discovery_requires_explicit_server_opt_in(orchestrator) -> None:
    assert "raw_execute" not in sdk_bridge.focused_tool_specs(orchestrator)
    assert "raw_execute" in sdk_bridge.focused_tool_specs(orchestrator, expose_raw=True)


def test_server_instructions_encode_the_verified_design_loop() -> None:
    instructions = sdk_bridge.SERVER_INSTRUCTIONS

    for required in (
        "get_phase", "semantic", "ActionReport", "assumptions", "inspect", "measure",
        "repair", "acceptance", "promote",
    ):
        assert required.lower() in instructions.lower(), required
    assert len(instructions) <= 700


# ------------------------------------------------------------------ calling through

def test_a_read_only_call_takes_no_write_lease(sdk, specs, orchestrator, fake_scene) -> None:
    """ADR-007's actual guarantee: many readers beside the one writer. A bridge that
    acquired the lock to answer ``get_phase`` would make a second agent's read contend
    with the builder, and the multi-agent story — Gate B 6.2's one must-be-excellent
    thing — stops holding."""
    result = sdk_bridge.call_tool(sdk, "get_phase", {}, specs=specs, orchestrator=orchestrator)

    assert result.is_error is False
    assert orchestrator.current() is None, "a read took the write lock"
    payload = result.structured_content
    assert payload["phase"] == Phase.BLOCKOUT.value
    assert "add_primitive" in payload["tools_callable_now"]


def test_a_mutating_call_takes_the_write_lease_under_one_holder(
    sdk, specs, orchestrator, fake_scene,
) -> None:
    """The transport passed no lease at all before this, so every mutating call over a
    live connection was refused with ``mcp.lock_required`` — the server would have
    connected and then been unable to build anything."""
    result = sdk_bridge.call_tool(
        sdk, "add_primitive",
        {"object_id": "box1", "kind": "cube", "size": [1.0, 1.0, 1.0]},
        specs=specs, orchestrator=orchestrator,
    )

    assert result.is_error is False, _text(result)
    assert fake_scene.applied_with_lease, "nothing reached the scene"
    assert fake_scene.applied_with_lease[-1].holder == sdk_bridge.LEASE_HOLDER


def test_two_mutating_calls_in_one_session_renew_rather_than_contend(
    sdk, specs, orchestrator,
) -> None:
    """One connected client is one logical writer. If the second call contended with the
    first, a client could make exactly one change per connection."""
    for index in (1, 2):
        result = sdk_bridge.call_tool(
            sdk, "add_primitive",
            {"object_id": f"box{index}", "kind": "cube", "size": [1.0, 1.0, 1.0]},
            specs=specs, orchestrator=orchestrator,
        )
        assert result.is_error is False, _text(result)


def test_a_result_arrives_as_both_text_and_structured_content(
    sdk, specs, orchestrator,
) -> None:
    """Clients differ: some render ``content`` for a human, some parse
    ``structuredContent`` for a model. Sending only one means half of them show nothing."""
    result = sdk_bridge.call_tool(sdk, "get_phase", {}, specs=specs, orchestrator=orchestrator)

    assert result.structured_content is not None
    assert json.loads(_text(result)) == result.structured_content


# ------------------------------------------------------------------ refusals

def test_a_phase_refusal_arrives_as_a_named_rule_with_a_next_step(
    sdk, specs, orchestrator,
) -> None:
    """Gate A 4.2, verbatim: the agent is told which rule broke and what to do next. Over a
    transport that means an *error result*, not a raised exception — an exception escaping
    ``on_call_tool`` reaches the client as an opaque JSON-RPC internal error with the rule,
    the phase and the fix all thrown away."""
    result = sdk_bridge.call_tool(
        sdk, "export_scene",
        {"object_ids": ["box1"], "path": "out.glb"},
        specs=specs, orchestrator=orchestrator,
    )

    assert result.is_error is True
    message = _text(result)
    assert "polish" in message, "the refusal does not say which phase would allow it"
    assert "promote_phase" in message, "the refusal offers no next step"
    assert result.structured_content["rule"], "no rule named"
    assert result.structured_content["suggestion"]


def test_an_unknown_tool_is_refused_with_the_shortlist_it_should_have_chosen_from(
    sdk, specs, orchestrator,
) -> None:
    """An agent that misnamed a tool needs the names that would have worked, in this phase
    — not the whole catalogue, and not a bare KeyError."""
    result = sdk_bridge.call_tool(sdk, "add_primitiv", {}, specs=specs, orchestrator=orchestrator)

    assert result.is_error is True
    assert result.structured_content["rule"] == "mcp.unknown_tool"
    assert "add_primitive" in _text(result)


def test_a_bad_parameter_is_refused_by_name_before_anything_is_locked(
    sdk, specs, orchestrator,
) -> None:
    """Params are checked before the lock (``dispatch``'s deliberate order). Through the
    bridge that has to stay true, or a malformed call would take the write lease and hold
    it against every other agent for nothing."""
    result = sdk_bridge.call_tool(
        sdk, "add_primitive", {"object_id": "box1", "kind": "dodecahedron", "size": [1, 1, 1]},
        specs=specs, orchestrator=orchestrator,
    )

    assert result.is_error is True
    assert orchestrator.current() is None, "a rejected call still took the write lock"
    assert "kind" in _text(result)


def test_an_unexpected_failure_still_names_a_rule_and_never_leaks_a_traceback(
    sdk, specs, orchestrator, monkeypatch,
) -> None:
    """The catch-all. Everything in this product raises ``RuleError``; anything that does
    not is a defect in forge3d, and the agent still has to be told which — otherwise it
    retries the same call forever. What it must *not* be told is a stack trace, which
    names our files and none of its own options.

    The failure is injected at ``dispatch`` rather than through a synthetic ``ToolSpec``
    because a spec the registry has never heard of is refused as an unknown tool long
    before any handler runs — it would have tested the wrong branch and passed."""
    def _boom(*_args, **_kwargs):
        raise ZeroDivisionError("boom")

    monkeypatch.setattr(sdk_bridge, "dispatch", _boom)
    result = sdk_bridge.call_tool(sdk, "get_phase", {}, specs=specs, orchestrator=orchestrator)

    assert result.is_error is True
    assert result.structured_content["rule"] == "mcp.unhandled_failure"
    assert result.structured_content["suggestion"]
    message = _text(result)
    assert "ZeroDivisionError" in message
    assert "Traceback" not in message and "sdk_bridge.py" not in message


# ------------------------------------------------------------------ the server object

def test_build_server_produces_a_server_the_installed_sdk_can_run(sdk, orchestrator) -> None:
    """The whole point of this file. Before it, ``_build_server`` refused by name because
    it wanted SDK 1.x decorators that 2.0.0 does not have, and nothing could connect over
    either transport."""
    server = sdk_bridge.build_server(sdk, orchestrator, name="blender-agent-mcp", version="0.1.0")

    assert isinstance(server, sdk.server.Server)
    assert callable(getattr(server, "run", None))
    assert callable(getattr(server, "streamable_http_app", None))

    options = server.create_initialization_options()
    assert options.server_name == "blender-agent-mcp"
    assert options.capabilities.tools is not None, "the server does not advertise tools"
    assert options.instructions == sdk_bridge.SERVER_INSTRUCTIONS


def test_an_sdk_without_the_2_0_callback_api_is_refused_by_name(sdk, orchestrator) -> None:
    """Replaces ``transports_test``'s SDK-1.x refusal test, which asserted the old, now
    obsolete direction. The knowledge it encoded is kept: an SDK this is not written
    against must produce one sentence naming what is missing, never an ``AttributeError``
    or a ``TypeError`` from inside someone else's package — the operator cannot tell from
    those which side is wrong."""
    class _WrongServer:
        def __init__(self, name: str) -> None:
            self.name = name

    broken = sdk_bridge.SdkModules(
        server=type("m", (), {"Server": _WrongServer}),
        types=sdk.types,
        stdio=sdk.stdio,
        transport="stdio",
    )
    with pytest.raises(RuntimeError) as excinfo:
        sdk_bridge.build_server(broken, orchestrator, name="x", version="0")

    assert not isinstance(excinfo.value, (AttributeError, TypeError))
    message = str(excinfo.value)
    assert "on_list_tools" in message
    assert "mcp" in message.lower()
