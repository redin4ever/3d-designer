"""A **real MCP client**, over a **real stdio pipe**, against a **real server subprocess**.

Every other test in this module calls ``dispatch`` in-process. That proved the decision
layer works and proved nothing at all about the thing Gate A 7.4 actually asked for —
*"make sure it supports my subscriptions eg: chatgpt subscription so that i can use it with
it"* — because for the whole build no client could connect. The transports were written
against the MCP SDK's 1.x decorator API, 2.0.0 removed it, and the failure was honest but
total.

So this file spawns ``python -m mcp_server``, connects the SDK's own ``ClientSession`` to
its stdin/stdout, and drives one complete journey the way a subscription client would:

    initialize -> tools/list -> get_phase -> add_primitive -> describe_object
               -> a call this phase forbids -> promote x3 -> export_scene -> a file on disk

The journey runs **once**, in a module-scoped fixture, and each test below reads the
transcript. A live round trip costs a subprocess and a Blender startup; paying that eight
times to assert eight things is how an end-to-end suite becomes the reason nobody runs the
suite. The cost of the sharing is that a dead journey fails every test at once — which is
the right failure, because a journey that died *is* the product being broken (Rule 6:
silence and success must never be the same shape, and here silence is impossible).

Determinism: the server gets a fresh scene (``build_app(reset_scene=True)``), no viewer
(nothing binds a port), an explicit ``PYTHONPATH`` rather than an inherited one, and a
wall-clock budget that turns a hang into a failure instead of a wedged run. The subprocess
is torn down by ``stdio_client``'s own shutdown sequence and the teardown is **asserted**,
not assumed — a leaked Blender process would hold the write lock and the export path
against every later run on this machine.

This is the one file in ``mcp_server`` that touches Blender, and only for the last step:
the fake engine's ``export_gltf`` records the call and returns the path without writing
anything, so "a real file appears on disk" is a question only a real engine can answer.
Everything before that step runs identically either way and is asserted either way.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp.client.stdio", reason="the MCP SDK is not installed here")

import anyio  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

_SRC = Path(__file__).resolve().parents[1]
_REPO = _SRC.parent

_BUDGET_SECONDS = 180.0
"""Whole-journey wall clock. Blender starts in well under a second here; this is a backstop
against a hang, not a performance target (Rule 6 — a stall is death that has not admitted
it)."""

_PID_LINE = re.compile(r"pid (\d+)")


# --------------------------------------------------------------------- the harness

def _server_params() -> StdioServerParameters:
    """The exact command a client would put in its own config, with nothing inherited.

    ``-X utf8`` because this text crosses a Windows console whose default encoding is
    cp1252, and ``PYTHONPATH`` explicitly because the SDK's stdio client passes only a
    small whitelist of environment variables through — an inherited one would make this
    test pass or fail depending on how the developer happened to launch pytest.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-m", "mcp_server", "--no-viewer"],
        env={"PYTHONPATH": str(_SRC), "PYTHONIOENCODING": "utf-8"},
        cwd=str(_REPO),
    )


def _process_is_alive(pid: int) -> bool:
    """Whether ``pid`` is still running, without signalling it.

    ``os.kill(pid, 0)`` is the portable idiom everywhere except Windows, where CPython maps
    it onto ``TerminateProcess`` — so the obvious liveness probe would *kill* the process it
    is asking about and the assertion would pass by causing what it tested for.
    """
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x00000102
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _payload(result: Any) -> dict[str, Any]:
    """What the tool actually answered, from whichever field the client got it in."""
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    return json.loads(_text(result))


def _text(result: Any) -> str:
    return "\n".join(block.text for block in result.content if getattr(block, "text", None))


# --------------------------------------------------------------------- the journey

async def _blockout(session: ClientSession, log: dict[str, Any]) -> None:
    """Orient, build, verify the geometry is really there, then try something the phase
    forbids — the four moves any connected agent makes in its first minute."""
    log["get_phase"] = _payload(await session.call_tool("get_phase", {}))

    log["add_primitive"] = await session.call_tool(
        "add_primitive", {"object_id": "box1", "kind": "cube", "size": [2.0, 1.0, 3.0]},
    )
    log["describe_object"] = await session.call_tool("describe_object", {"object_id": "box1"})
    log["list_objects"] = _payload(await session.call_tool("list_objects", {}))

    # EXPORT is legal only in POLISH (contracts.PHASE_ROLES). The refusal has to name the
    # phase and the way to reach it, and the next step below is us taking it at its word.
    log["forbidden"] = await session.call_tool(
        "export_scene", {"object_ids": ["box1"], "path": log["export_path"]},
    )


async def _promote_to_polish(session: ClientSession, log: dict[str, Any]) -> None:
    """Follow the refusal's own instruction. Three promotions, each gated on the phase's
    acceptance queries passing against live geometry (ADR-012 — there is no force)."""
    promotions = []
    for _ in range(3):
        result = await session.call_tool("promote_phase", {})
        promotions.append(result)
        if result.is_error:
            break
    log["promotions"] = promotions
    log["phase_after_promotion"] = _payload(await session.call_tool("get_phase", {}))


async def _drive(export_path: str, errlog: Any) -> dict[str, Any]:
    log: dict[str, Any] = {"export_path": export_path}
    with anyio.fail_after(_BUDGET_SECONDS):
        async with stdio_client(_server_params(), errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                log["initialize"] = await session.initialize()
                log["tools"] = (await session.list_tools()).tools
                await _blockout(session, log)
                await _promote_to_polish(session, log)
                log["export"] = await session.call_tool(
                    "export_scene", {"object_ids": ["box1"], "path": export_path},
                )
    return log


@pytest.fixture(scope="module")
def journey(tmp_path_factory) -> dict[str, Any]:
    """One complete live session, driven once and shared. See the module docstring."""
    workspace = tmp_path_factory.mktemp("live-mcp")
    export_path = str(workspace / "live.glb")
    stderr_path = workspace / "server.stderr"

    with open(stderr_path, "w", encoding="utf-8", errors="replace") as errlog:
        log = anyio.run(_drive, export_path, errlog)

    log["stderr"] = stderr_path.read_text(encoding="utf-8", errors="replace")
    match = _PID_LINE.search(log["stderr"])
    log["pid"] = int(match.group(1)) if match else None
    return log


# --------------------------------------------------------------------- what it proves

def test_a_real_client_completes_the_handshake(journey) -> None:
    """The single fact that was false for the whole build: something can connect."""
    info = journey["initialize"].server_info
    assert info.name == "blender-agent-mcp"
    assert journey["initialize"].capabilities.tools is not None


def test_tools_list_returns_the_real_catalogue_with_each_tools_role(journey) -> None:
    """A client renders what ``tools/list`` returns and nothing else. Names an agent cannot
    see are names it cannot call, and a tool with no role is one it cannot reason about
    before being refused."""
    by_name = {tool.name: tool for tool in journey["tools"]}

    assert {"get_phase", "list_objects", "describe_object", "promote_phase"} <= set(by_name)
    assert {"add_primitive", "add_wall", "export_scene"} <= set(by_name)
    assert by_name["add_primitive"].meta["roles"] == ["blockout"]
    assert by_name["get_phase"].meta["roles"] == ["inspect"]
    assert by_name["export_scene"].meta["roles"] == ["export"]
    assert by_name["add_primitive"].input_schema["properties"]["kind"]["enum"]


def test_the_raw_execution_tool_reaches_the_client_unnarrowed(journey) -> None:
    """Gate A 7.2 chose unrestricted arbitrary code execution for connected agents, with
    the CVSS 9.0 precedent stated in the option text, and 7.4 chose unrestricted filesystem
    access. Quietly withholding that capability at the transport — a sandbox, an allowlist,
    an AST check — would be as much a defect as never building it."""
    assert "raw_execute" in {tool.name for tool in journey["tools"]}


def test_get_phase_round_trips_and_parses(journey) -> None:
    """The tool an agent is told to call first, and after any refusal it did not expect."""
    phase = journey["get_phase"]
    assert phase["phase"] == "blockout"
    assert phase["next_phase"] == "refine"
    assert "add_primitive" in phase["tools_callable_now"]
    assert phase["summary"]


def test_a_mutating_call_builds_geometry_that_is_really_there_afterwards(journey) -> None:
    """End to end, through the transport, into Blender and back out again — measured, not
    reported. ``add_primitive`` saying ok proves the call arrived; ``describe_object``
    returning the dimensions we asked for proves the geometry exists."""
    added = journey["add_primitive"]
    assert added.is_error is False, _text(added)

    described = journey["describe_object"]
    assert described.is_error is False, _text(described)
    assert _payload(described)["dimensions"] == [2.0, 1.0, 3.0]
    assert _payload(described)["triangle_count"] > 0
    assert journey["list_objects"]["total"] == 1


def test_a_call_the_phase_forbids_reaches_the_client_as_a_named_rule_with_a_next_step(
    journey,
) -> None:
    """Gate A 4.2, verbatim: the agent is told which rule broke. Over a transport that
    means an error *result* — an exception escaping the handler arrives as an opaque
    JSON-RPC internal error with the rule, the phase and the fix all discarded, and the
    agent retries the same failing call forever."""
    refused = journey["forbidden"]
    assert refused.is_error is True
    message = _text(refused)

    assert refused.structured_content["rule"], "no rule named"
    assert "polish" in message, "does not say which phase would allow it"
    assert "promote_phase" in message, "offers no next step"
    assert "Traceback" not in message


def test_following_that_next_step_actually_gets_there(journey) -> None:
    """A suggestion that does not work is worse than none — this is the difference between
    a refusal that teaches and one that only sounds like it does. ADR-012 removed the
    promotion override, so these three promotions each passed real acceptance queries
    against real geometry."""
    for result in journey["promotions"]:
        assert result.is_error is False, _text(result)
    assert journey["phase_after_promotion"]["phase"] == "polish"


def test_export_scene_writes_a_real_file_a_person_can_open(journey) -> None:
    """The user's own definition of "it worked": a file they can open in Roblox, produced
    through the only interface an agent has. Gate A 6.3 — export always writes and reports
    what is wrong in a banner rather than blocking."""
    exported = journey["export"]
    assert exported.is_error is False, _text(exported)
    payload = _payload(exported)
    assert payload["ok"] is True
    assert payload["banner"]

    backend = journey["stderr"]
    if "engine: bpy" not in backend:
        pytest.skip(
            "the server fell back to the in-memory engine, whose export_gltf records the "
            "call without writing — every step above was still asserted"
        )
    written = Path(journey["export_path"])
    assert written.exists(), "export reported ok and produced no file"
    assert written.stat().st_size > 0


def test_the_server_subprocess_does_not_outlive_the_session(journey) -> None:
    """A leaked Blender process holds the write lock and the export path against every
    later run on this machine — one flaky teardown quietly wedges the whole suite."""
    assert journey["pid"] is not None, "the server never announced its pid on stderr"
    assert not _process_is_alive(journey["pid"])
