"""``python -m mcp_server`` — the command an MCP client launches.

This is the line a user pastes into Claude Desktop's ``claude_desktop_config.json``, into
Cursor's MCP settings, or into a ChatGPT developer-mode connector (with ``--http``). It
exists because "connect a client to it" needs a *command*, and until now the only entry
point was ``forge3d serve``, which is not on anybody's PATH.

It is a composition *caller*, not a composition root: ``app.build_app`` still owns the
wiring, and this file only decides which transport to hand the result to and how to keep
the pipe clean while it starts up. Both imports are function-local — ``app`` imports
``mcp_server``, so importing it at module scope would make the package unimportable.
"""

from __future__ import annotations

import argparse
import os
import sys

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:  # `python -m mcp_server` from anywhere, not just with src/ on PYTHONPATH
    sys.path.insert(0, _SRC)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m mcp_server", description=__doc__)
    parser.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-blender", action="store_true", help="force the in-memory engine")
    parser.add_argument("--no-raw", action="store_true", help="omit the raw-execution tool")
    parser.add_argument("--no-viewer", action="store_true", help="do not attach the live view")
    return parser.parse_args(argv)


class _StdoutHeldOpen:
    """Point fd 1 at stderr for the duration of engine startup, then give the pipe back.

    On a stdio connection fd 1 **is** the JSON-RPC wire, and Blender writes to it — an
    "INFO Draco is available" line at export time, assorted chatter at import. One stray
    line is a parse error at the client and, because it arrives before the handshake
    completes, it looks to the user exactly like the server failing to start.

    The SDK's own ``stdio_server`` does this while it is serving. Nothing covers the window
    before that, which is precisely where ``build_app`` loads Blender, so this covers it:
    duplicate the real stdout somewhere safe, point fd 1 at stderr, and restore it just
    before the transport claims the descriptor. A no-op under ``--http``, where fd 1 is
    nothing more special than a console.
    """

    def __init__(self) -> None:
        self._saved: int | None = None

    def __enter__(self) -> "_StdoutHeldOpen":
        try:
            self._saved = os.dup(1)
            os.dup2(2, 1)
        except OSError:  # no real fds (embedded, or a pytest capture layer) — nothing to protect
            self._saved = None
        return self

    def release(self) -> None:
        if self._saved is None:
            return
        try:
            os.dup2(self._saved, 1)
        finally:
            os.close(self._saved)
            self._saved = None

    def __exit__(self, *_exc: object) -> None:
        self.release()


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)

    with _StdoutHeldOpen() as wire:
        from app import build_app

        app = build_app(
            prefer_blender=not args.no_blender,
            include_raw=not args.no_raw,
            attach_viewer=not args.no_viewer,
        )
        # stderr, always: on stdio it is the only stream a person will ever see, and on
        # HTTP it keeps the startup banner out of any log that is parsing responses. The
        # pid is here so a wedged server can be found and killed without guessing.
        print(f"forge3d mcp server — pid {os.getpid()}, transport "
              f"{'streamable-http' if args.http else 'stdio'}", file=sys.stderr)
        print(app.describe(), file=sys.stderr)
        sys.stderr.flush()
        wire.release()

        from .transports import serve_http, serve_stdio

        if args.http:
            serve_http(app.orchestrator, host=args.host, port=args.port)
        else:
            serve_stdio(app.orchestrator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
