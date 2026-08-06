"""``forge3d`` — the command line entry point declared in ``pyproject.toml``.

Four things a person actually wants to do:

    forge3d run                 start everything and open the live view — the one command
    forge3d connect             the exact config to point Claude / Cursor at this
    forge3d doctor              what is installed, what works, what does not
    forge3d serve --stdio       expose the tools to Claude Desktop / Claude Code / Cursor
    forge3d serve --http        expose them to a ChatGPT developer-mode connector

``run`` exists because ``serve`` cannot be it: on stdio it blocks waiting for a client on
its own pipes, which is right for a desktop client launching it and useless for a person
who wants to look at the thing. ``run`` starts the engine, the viewer socket, an HTTP MCP
endpoint and the frontend, and opens a browser at it.

``doctor`` exists because this system has several independent optional pieces — Blender,
the MCP SDK, the websocket transport — and each degrades differently. A single command that
says which are present turns three confusing failures into one clear answer.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# A Windows console defaults to cp1252, which cannot encode an em dash — and this tool's
# error messages, defect reports and export banners are full of them. Without this, the
# first clipping defect printed on the primary target platform raises UnicodeEncodeError
# and takes down whatever was reporting it. Only the entry point does this; a library must
# not reconfigure its caller's streams.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # already redirected, or not a text stream
        pass

__all__ = ["main", "doctor"]


def _probe(label: str, fn) -> tuple[str, bool, str]:
    try:
        return (label, True, str(fn()))
    except Exception as exc:  # noqa: BLE001 — reporting failures is the whole job
        return (label, False, f"{type(exc).__name__}: {exc}")


def doctor() -> int:
    """Report what is actually available. Returns 0 if the core works, 1 if it does not."""
    from app import build_app

    checks = [
        _probe("Blender (bpy)", lambda: __import__("bpy").app.version_string),
        _probe("MCP SDK", lambda: __import__("mcp").__name__),
        _probe("websockets", lambda: __import__("websockets").__version__),
    ]

    print("forge3d doctor\n")
    for label, ok, detail in checks:
        print(f"  {'OK  ' if ok else 'MISS'}  {label:16} {detail}")

    print()
    app = build_app(prefer_blender=True, attach_viewer=False)
    print(app.describe())

    core_ok = bool(app.handlers) and bool(app.registry)
    print()
    if not app.handlers:
        print("  FAIL  no operations registered — nothing can be built")
    if not app.registry:
        print("  FAIL  no tool registry — no agent can call anything")
    if app.backend == "fake":
        print("  WARN  running on the in-memory engine. It is enough to exercise the")
        print("        system end to end, but its primitives are bounding boxes and its")
        print("        booleans do not cut, so nothing it produces is a usable asset.")
    if core_ok:
        print("  Core is wired and callable.")
    return 0 if core_ok else 1


def start_viewer(app: Any, host: str, port: int) -> str:
    """Start the live-view socket on a daemon thread, and say what happened.

    Gate B 1.3 chose auto-start: the 3D view, the action log, the cadence menu and
    pause/rollback/redirect were all built, tested and real for a whole pass, and
    ``forge3d serve`` never opened the socket that would let a browser reach any of them.
    ``viewer.serve()`` was exported and imported nowhere outside its own package.

    Its own thread because the two servers both want to own an event loop:
    ``serve_stdio`` ends in a blocking ``anyio.run``. ``ViewerSocketServer`` is already
    built for this — it wakes its flush loop with ``loop.call_soon_threadsafe``, precisely
    so the scene can queue a message from whichever thread applied the operation.

    Daemon, so a viewer that hangs cannot keep the process alive after the agent session
    ends. Never fatal: a missing ``websockets``, or a port already taken, costs the live
    view and must not cost the agent its tools. Returns a line for the banner either way —
    silence here would leave a user staring at a page that will never connect, with
    nothing anywhere saying why.
    """
    import threading

    try:
        import viewer as viewer_module

        server = viewer_module.serve(app.scene, app.orchestrator, host=host, port=port)

        # The arrow the whole live view was missing. `ViewerBridge.report_action` already
        # knew how to turn an ActionReport into HIGHLIGHT / LOG / PROBLEMS messages and
        # nothing ever called it, so a person watching saw meshes appear and was told
        # nothing about what the agent had just done or found. Wired here, in the
        # composition root, because the dependency arrow points from the web layer into the
        # core and never back — `orchestration` must not learn that `viewer` exists.
        app.orchestrator.on_report(server.bridge.report_action)
    except Exception as exc:  # noqa: BLE001
        return f"  live view: unavailable ({exc}). The tools are unaffected."

    failure: list[str] = []

    def _run() -> None:
        import asyncio

        async def _main() -> None:
            async with server:
                await server.serve_forever()

        try:
            asyncio.run(_main())
        except Exception as exc:  # noqa: BLE001
            failure.append(str(exc))

    threading.Thread(target=_run, name="forge3d-viewer", daemon=True).start()

    # Give the bind a moment to fail loudly rather than reporting a URL that never answers.
    time.sleep(0.25)
    if failure:
        return f"  live view: could not start ({failure[0]}). The tools are unaffected."
    return f"  live view: ws://{host}:{port} — open frontend/index.html to watch"


def serve(args: argparse.Namespace) -> int:
    from app import build_app

    app = build_app(prefer_blender=not args.no_blender, include_raw=not args.no_raw)
    print(app.describe(), file=sys.stderr)

    if not args.no_viewer:
        print(start_viewer(app, args.viewer_host, args.viewer_port), file=sys.stderr)
    else:
        print("  live view: off (--no-viewer)", file=sys.stderr)

    if args.http and args.host not in ("127.0.0.1", "localhost", "::1"):
        # ADR-009: connected agents get unrestricted code execution and unrestricted
        # filesystem access, by explicit decision. On loopback the trust boundary is the
        # user's own machine. Off loopback it is whoever can route to this port.
        print(
            f"\n  WARNING: binding to {args.host}, not loopback.\n"
            "  This server grants connected agents unrestricted code execution and full\n"
            "  filesystem access (ADR-009). Off loopback, anything that can reach this\n"
            "  port has that. Bind 127.0.0.1 unless you specifically intend otherwise.\n",
            file=sys.stderr,
        )

    try:
        if args.http:
            from mcp_server import serve_http

            return serve_http(app.orchestrator, host=args.host, port=args.port) or 0
        from mcp_server import serve_stdio

        return serve_stdio(app.orchestrator) or 0
    except Exception as exc:  # noqa: BLE001
        print(f"\n  Could not start the server: {exc}", file=sys.stderr)
        print("  Run `forge3d doctor` to see which pieces are missing.", file=sys.stderr)
        return 1


def connect(args: argparse.Namespace) -> int:
    """``forge3d connect`` — print, or write, the config an AI client needs."""
    from app.connect import CLIENTS, describe, write_config

    if args.write:
        if args.client in (None, "chatgpt"):
            known = ", ".join(sorted(CLIENTS))
            print(file=sys.stderr)
            print("  --write needs a specific stdio client, e.g.:", file=sys.stderr)
            print("    forge3d connect claude-desktop --write", file=sys.stderr)
            print(f"  Known: {known}", file=sys.stderr)
            print(file=sys.stderr)
            return 1
        try:
            path = write_config(args.client)
        except (KeyError, RuntimeError) as exc:
            print(file=sys.stderr)
            print(f"  {exc}", file=sys.stderr)
            print(file=sys.stderr)
            return 1
        print()
        print(f"  Wrote forge3d into {path}")
        print(f"  {CLIENTS[args.client]['note']}")
        print()
        return 0

    print()
    print("forge3d connect")
    print(describe(args.client, http_port=args.port))
    print()
    return 0


def run(args: argparse.Namespace) -> int:
    """``forge3d run`` — everything at once. See ``app/live.py`` for what and why."""
    from app.live import run_live

    return run_live(
        prefer_blender=not args.no_blender,
        include_raw=not args.no_raw,
        ports={"mcp": args.port, "viewer": args.viewer_port, "web": args.web_port},
        open_browser=not args.no_browser,
        seed=not args.empty,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge3d", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="report what is installed and whether the core is wired")

    c = sub.add_parser("connect", help="the exact config to point an AI client at this")
    c.add_argument("client", nargs="?", default=None,
                   help="claude-desktop | claude-code | cursor | chatgpt (default: all)")
    c.add_argument("--write", action="store_true",
                   help="merge it into the client's own config file rather than printing it")
    c.add_argument("--port", type=int, default=8765, help="the HTTP MCP port forge3d run uses")

    r = sub.add_parser("run", help="start everything and open the live view (the one command)")
    r.add_argument("--port", type=int, default=8765, help="MCP over streamable HTTP")
    r.add_argument("--viewer-port", type=int, default=8766)
    r.add_argument("--web-port", type=int, default=8767)
    r.add_argument("--no-blender", action="store_true", help="force the in-memory engine")
    r.add_argument("--no-raw", action="store_true", help="omit the unrestricted-execution tool")
    r.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    r.add_argument("--empty", action="store_true",
                   help="start with an empty scene instead of the demo geometry")

    s = sub.add_parser("serve", help="expose the tools over MCP")
    s.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-blender", action="store_true", help="force the in-memory engine")
    s.add_argument("--no-raw", action="store_true", help="omit the unrestricted-execution tool")
    # Gate B 1.3 chose auto-start, so this is opt-OUT. The live view stays on loopback for
    # the same reason the MCP HTTP transport does (A-005, ADR-009): a connected agent has
    # unrestricted execution, and nothing about that is safe to expose off-host.
    s.add_argument("--no-viewer", action="store_true", help="do not start the live-view socket")
    s.add_argument("--viewer-host", default="127.0.0.1")
    s.add_argument("--viewer-port", type=int, default=8766)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "doctor":
        return doctor()
    if args.command == "connect":
        return connect(args)
    if args.command == "run":
        return run(args)
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
