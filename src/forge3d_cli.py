"""``forge3d`` — the command line entry point declared in ``pyproject.toml``.

Three things a person actually wants to do:

    forge3d doctor              what is installed, what works, what does not
    forge3d serve --stdio       expose the tools to Claude Desktop / Claude Code / Cursor
    forge3d serve --http        expose them to a ChatGPT developer-mode connector

``doctor`` exists because this system has several independent optional pieces — Blender,
the MCP SDK, the websocket transport — and each degrades differently. A single command that
says which are present turns three confusing failures into one clear answer.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

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


def serve(args: argparse.Namespace) -> int:
    from app import build_app

    app = build_app(prefer_blender=not args.no_blender, include_raw=not args.no_raw)
    print(app.describe(), file=sys.stderr)

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge3d", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="report what is installed and whether the core is wired")

    s = sub.add_parser("serve", help="expose the tools over MCP")
    s.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-blender", action="store_true", help="force the in-memory engine")
    s.add_argument("--no-raw", action="store_true", help="omit the unrestricted-execution tool")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "doctor":
        return doctor()
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
