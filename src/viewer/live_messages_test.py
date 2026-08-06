"""Each newly-emitted wire type, proved by a real client actually receiving it.

``report_test.py`` proves the bridge builds these messages. That is not the same claim: a
message correctly built and queued on a transport nobody drains is exactly the state this
module was already in — five wire types the browser fully implemented, none of which ever
crossed a socket. So every type this module newly constructs is asserted here at the far
end of a real connection, in the JSON shape ``frontend/src/socket.js`` parses.
"""

from __future__ import annotations

from contracts import (
    ActionReport,
    Conflict,
    Defect,
    DefectClass,
    ExportReport,
    Proposal,
    RunState,
    Severity,
)


def _report(**overrides) -> ActionReport:
    fields = dict(op_id="op1", ok=True, summary="add_railing applied", changed=("rail_a",))
    fields.update(overrides)
    return ActionReport(**fields)


def _conflict() -> Conflict:
    return Conflict(
        conflict_id="c1",
        proposals=(
            Proposal(proposal_id="p1", author="agent-a", target_objects=("wall",), operation_kind="move"),
            Proposal(proposal_id="p2", author="agent-b", target_objects=("wall",), operation_kind="attach"),
        ),
        overlapping_objects=("wall",),
        detail="both touch wall",
    )


def test_a_client_receives_the_highlight_for_what_just_changed(
    sockets, real_scene, add_cube_op
) -> None:
    """Gate A 5.3 end to end. The single most visible thing the live view does, and the
    thing it did not do."""

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                real_scene.apply(add_cube_op("op1", "wall_a"))
                return await sockets.recv_until(ws, "highlight")

    message = sockets.run(main)

    assert message["object_ids"] == ["wall_a"]


def test_a_client_receives_the_action_log_line(sockets, real_scene) -> None:
    """The action log carried connection status and nothing else. This is the line that
    tells a watching human what the agent just did."""

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                server.bridge.report_action(_report())
                return await sockets.recv_until(ws, "log")

    message = sockets.run(main)

    assert "add_railing applied" in message["text"]
    assert message["data"]["changed"] == ["rail_a"]


def test_a_client_receives_the_problems_an_action_introduced(sockets, real_scene) -> None:
    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                server.bridge.report_action(
                    _report(
                        new_problems=(
                            Defect(
                                defect_class=DefectClass.PART_CLIPPING,
                                severity=Severity.BLOCKER,
                                object_id="rail_a",
                                detail="clips the tread by 12mm",
                                magnitude=0.012,
                            ),
                        )
                    )
                )
                return await sockets.recv_until(ws, "problems")

    message = sockets.run(main)

    assert message["data"]["new"][0]["object_id"] == "rail_a"
    assert message["data"]["new"][0]["defect_class"] == DefectClass.PART_CLIPPING.value
    assert "clips the tread by 12mm" in message["text"]


def test_a_client_receives_the_export_banner(sockets, real_scene) -> None:
    """Gate A 6.3. The banner is about a file that was written; it reaches the operator
    over its own channel or it reaches nobody."""

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                server.bridge.report_export(
                    ExportReport(path="out/house.glb", profile="roblox", ok=True, triangle_count=900)
                )
                return await sockets.recv_until(ws, "export_report")

    message = sockets.run(main)

    assert "out/house.glb" in message["text"]
    assert message["data"]["profile"] == "roblox"


def test_a_client_receives_a_conflict_with_the_geometry_attached(sockets, real_scene) -> None:
    """Gate A 10.3 — never resolved silently, and never announced without the objects
    involved."""

    async def main():
        async with sockets.serving(real_scene) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                server.bridge.report_conflicts(_conflict())
                return await sockets.recv_until(ws, "conflict")

    message = sockets.run(main)

    assert message["object_ids"] == ["wall"]
    assert "agent-a" in message["text"]


def test_a_client_receives_a_run_state_change_it_did_not_ask_for(
    sockets, real_scene, recording_orchestrator
) -> None:
    """A run paused by anything other than this browser — the agent itself, another
    operator, a blocked phase — must still show as paused here."""

    async def main():
        async with sockets.serving(real_scene, recording_orchestrator) as server:
            async with sockets.client(server) as ws:
                await sockets.handshake(ws)
                recording_orchestrator.pause()
                server.bridge.report_run_state()
                return await sockets.recv_until(ws, "run_state")

    message = sockets.run(main)

    assert message["text"] == RunState.PAUSED.value


def test_a_connecting_client_is_told_the_current_run_state_immediately(
    sockets, real_scene, recording_orchestrator
) -> None:
    """Opening the page during a paused run must not show "running". The state exists
    before the connection does, so it has to be part of the handshake rather than
    something the client waits for a change to learn."""
    recording_orchestrator.pause()

    async def main():
        async with sockets.serving(real_scene, recording_orchestrator) as server:
            async with sockets.client(server) as ws:
                return await sockets.recv_until(ws, "run_state")

    message = sockets.run(main)

    assert message["text"] == RunState.PAUSED.value
