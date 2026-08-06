"""The composition root's `serve` command, tested for the wires that were never connected.

`src/app/app_test.py` proves the pieces are assembled. This file proves the *entry point*
actually starts them — a distinction that cost a whole pass: `viewer.serve()` was real,
exported, tested, and imported nowhere outside its own package, so every browser feature the
user chose at Gate A 5.1/5.3/3.1/5.4 was unreachable from a running server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket

import pytest

from app import build_app
from forge3d_cli import main, start_viewer


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_serve_command_starts_the_viewer_by_default() -> None:
    """Gate B 1.3 chose auto-start over a flag: 'no extra steps'. If this becomes opt-in,
    the live view silently goes back to being something you have to know to ask for."""
    parser_args = _parse(["serve"])
    assert parser_args.no_viewer is False


def test_the_viewer_can_be_turned_off_without_touching_the_tools() -> None:
    """A headless run should not have to accept a listening socket it will never use."""
    assert _parse(["serve", "--no-viewer"]).no_viewer is True


def test_the_viewer_binds_loopback_by_default() -> None:
    """A-005 and ADR-009. Every connected agent has unrestricted code execution and full
    filesystem access by explicit user choice; on loopback the trust boundary is this
    machine, and off loopback it is anything that can route to the port."""
    assert _parse(["serve"]).viewer_host == "127.0.0.1"


def test_the_viewer_and_the_mcp_transport_do_not_share_a_port() -> None:
    """They are two servers on one process. Defaulting both to 8765 would make the live
    view fail to bind on every ordinary `forge3d serve`, reported only as a banner line."""
    args = _parse(["serve"])
    assert args.port != args.viewer_port


@pytest.mark.timeout(30)
def test_a_browser_can_actually_reach_a_running_session() -> None:
    """The whole point. This is the wire that did not exist: `forge3d serve` built an app
    and never opened the socket, so `frontend/index.html` connected to nothing, forever.

    Asserts a real client gets a real first frame — not that a thread was created.
    """
    pytest.importorskip("websockets")
    app = build_app(prefer_blender=False, attach_viewer=False)
    port = _free_port()

    banner = start_viewer(app, "127.0.0.1", port)
    assert str(port) in banner, f"the banner must tell a person where to look: {banner!r}"

    async def probe() -> dict:
        import websockets

        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            return json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

    first = asyncio.run(probe())
    assert first["type"], f"connected but received nothing usable: {first!r}"
    assert "seq" in first, "every server message carries a seq — the client reconciles on it"


@pytest.mark.timeout(30)
def test_a_viewer_that_cannot_start_costs_the_live_view_and_not_the_tools() -> None:
    """A port already in use is the ordinary case — a second `forge3d serve`, or anything
    else on 8766. Losing the agent's entire tool surface to that would be absurd, and a
    silent failure would leave a person watching a page that never connects."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    port = _free_port()

    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", port))
        blocker.listen(1)
        banner = start_viewer(app, "127.0.0.1", port)

    assert "live view" in banner.lower()
    assert "unaffected" in banner.lower(), (
        f"the banner must say the tools still work, or a person assumes nothing does: {banner!r}"
    )


def _parse(argv: list[str]) -> argparse.Namespace:
    """Drive the real parser `main` builds, so a renamed flag fails here."""
    captured: dict[str, argparse.Namespace] = {}

    import forge3d_cli

    original = forge3d_cli.serve
    try:
        forge3d_cli.serve = lambda args: captured.setdefault("args", args) and 0
        main(argv)
    except SystemExit:  # argparse rejected the arguments
        raise
    finally:
        forge3d_cli.serve = original
    return captured["args"]
