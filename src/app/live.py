"""``forge3d run`` — one command that starts the whole product and opens the browser.

Everything needed to actually *use* this was reachable before and none of it was reachable
**together**. ``forge3d serve`` starts the MCP transport on stdio, which means it blocks
waiting for a client on its own stdin — correct for Claude Desktop or Cursor launching it,
useless for a person who wants to look at the thing. And the browser page is a static file
nobody serves, so opening it means finding it on disk. A product whose demo requires three
terminals and a file:// URL does not have an entry point; it has parts.

This is the entry point. Three servers, one process:

    127.0.0.1:8765   MCP over streamable HTTP  — where an agent connects
    127.0.0.1:8766   the viewer websocket      — where the browser watches
    127.0.0.1:8767   the frontend itself       — what the browser opens

HTTP rather than stdio for MCP, deliberately: stdio can serve exactly one client that owns
the process's own pipes, and this command exists so a person and an agent can both be
present at once. ``forge3d serve`` remains the stdio entry point and is what a desktop
client's config should name.

The frontend needs a real origin. It is static ES modules with no build step, and a browser
refuses `import` over ``file://`` — so serving it is not a convenience, it is the difference
between a working page and a blank one with a console error nobody sees.

Every listener binds loopback and none of them takes a host argument. ADR-009 grants every
connected agent arbitrary code execution and unrestricted filesystem access by the user's
explicit choice at Gate A 7.2/7.4; on loopback the trust boundary is this machine. Widening
that belongs behind the deliberate flag on ``forge3d serve --http --host``, where the
warning naming ADR-009 already lives, and not in the convenient command.
"""

from __future__ import annotations

import functools
import http.server
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

__all__ = ["run_live", "FRONTEND_DIR", "DEFAULT_PORTS"]

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

DEFAULT_PORTS = {"mcp": 8765, "viewer": 8766, "web": 8767}
"""The viewer port is not free to change: ``frontend/src/main.js`` hardcodes
``ws://127.0.0.1:8766`` as its default, matching ``viewer.serve()``'s own default. Three
places already agree on it; a fourth opinion here would be the one that breaks the page."""


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    """Whether ``port`` can be bound right now.

    Checked up front for all three, because the failure it prevents is the confusing one: a
    second ``forge3d run`` starts, one listener silently loses the race, and the user gets a
    page that loads and never receives a frame — with nothing anywhere saying why.
    """
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static files, plus the two endpoints the Connect button needs.

    ``SimpleHTTPRequestHandler`` writes a line per request to stderr, which on this command
    is the same stream carrying the startup banner and the engine's own output. Twenty
    module fetches would push the URLs a person needs off the top of their terminal, so it
    is silenced.

    The API lives here rather than on the wire protocol because connecting an AI client is
    a one-off setup action, not a live-run event — ``contracts.wire`` is for what is
    happening to the scene, and putting setup traffic through it would widen a frozen
    surface for something that is not about geometry at all. Being served from the same
    origin as the page is also what keeps this a plain ``fetch`` with no CORS.
    """

    def log_message(self, *_args: Any) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # No caching: "which clients are installed" and "is forge3d configured" both change
        # underneath the page, and a stale answer here means a button that lies.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's own naming
        if self.path.startswith("/textures/"):
            from app.texture_assets import TextureAssetError, resolve_texture_asset

            parts = self.path.split("?", 1)[0].split("/")
            if len(parts) != 4:
                self.send_error(404)
                return
            try:
                asset = resolve_texture_asset(self.managed_texture_root, parts[2], parts[3])
                body = asset.path.read_bytes()
            except (TextureAssetError, OSError):
                self.send_error(404)
                return
            self.send_response(200)
            for name, value in asset.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/api/clients":
            from app.connect import detect_clients

            self._json(200, {"clients": detect_clients()})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/api/connect":
            self.send_error(404)
            return

        from app.connect import CLIENTS, write_config

        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (TypeError, ValueError):
            self._json(400, {"error": "the request body was not JSON"})
            return

        client = body.get("client")
        # Only the clients this build knows about, by name. Not a sandbox — ADR-009 already
        # grants connected agents full disk access by explicit choice — but there is no
        # reason for a setup endpoint to accept an arbitrary path, and building one that
        # did would be inventing a capability nobody asked for.
        if client not in CLIENTS:
            self._json(400, {"error": f"unknown client {client!r}"})
            return

        try:
            path = write_config(client)
        except (KeyError, RuntimeError, OSError) as exc:
            self._json(500, {"error": str(exc)})
            return

        self._json(200, {"ok": True, "client": client, "path": str(path),
                         "note": CLIENTS[client]["note"]})


def serve_frontend(port: int, directory: Path) -> http.server.ThreadingHTTPServer:
    """Serve ``directory`` on loopback, on a daemon thread, and return the server."""
    _QuietHandler.managed_texture_root = directory.parent / ".forge3d" / "textures"
    handler = functools.partial(_QuietHandler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, name="forge3d-web", daemon=True).start()
    return httpd


def run_live(
    *,
    prefer_blender: bool = True,
    include_raw: bool = True,
    ports: dict[str, int] | None = None,
    open_browser: bool = True,
    seed: bool = True,
    ready: threading.Event | None = None,
) -> int:
    """Start everything, open the browser, and block until interrupted.

    ``ready`` is set once all three listeners are up and the scene is reachable — the hook a
    test needs so it can drive the thing rather than sleep and hope.
    """
    from app import build_app

    ports = {**DEFAULT_PORTS, **(ports or {})}

    taken = [name for name, port in ports.items() if not port_is_free(port)]
    if taken:
        detail = ", ".join(f"{name} ({ports[name]})" for name in taken)
        print(
            f"\n  Port already in use: {detail}.\n"
            "  Another forge3d is probably already running — use it, or stop it first.\n",
            file=sys.stderr,
        )
        return 1

    app = build_app(prefer_blender=prefer_blender, include_raw=include_raw, attach_viewer=False)
    print(app.describe(), file=sys.stderr)

    # Seeded by default, because the alternative is what this command used to do: open a
    # working live view of an empty room, with no way for the person looking at it to put
    # anything in. Geometry only ever arrives from a connected agent, so "there are no
    # meshes" was an accurate description of the product rather than a misunderstanding of
    # it. `--empty` opts out, for anyone attaching their own agent straight away.
    if seed:
        from app.demo_scene import seed_scene

        print(seed_scene(app).describe(), file=sys.stderr)

    from forge3d_cli import start_viewer

    print(start_viewer(app, "127.0.0.1", ports["viewer"]), file=sys.stderr)

    if not FRONTEND_DIR.is_dir():
        print(f"  frontend: missing at {FRONTEND_DIR} — the live view will not load", file=sys.stderr)
        web = None
    else:
        web = serve_frontend(ports["web"], FRONTEND_DIR)
        print(f"  frontend: http://127.0.0.1:{ports['web']}/index.html", file=sys.stderr)

    url = f"http://127.0.0.1:{ports['web']}/index.html"
    print(
        f"\n  Watch it:   {url}\n"
        f"  Agents:     http://127.0.0.1:{ports['mcp']}/mcp  (streamable HTTP)\n"
        f"  Stdio MCP:  python -m mcp_server   (for Claude Desktop / Cursor)\n"
        "\n  Drag to orbit, scroll to zoom. Arrow keys and +/- work too.\n"
        "  Ctrl-C to stop.\n",
        file=sys.stderr,
    )

    if open_browser and web is not None:
        # Never fatal: a headless box, a container, or a machine with no default browser is
        # a perfectly ordinary place to run this, and the URL is already printed above.
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    if ready is not None:
        ready.set()

    from mcp_server import serve_http

    try:
        serve_http(app.orchestrator, host="127.0.0.1", port=ports["mcp"])
    except KeyboardInterrupt:
        print("\n  Stopped.", file=sys.stderr)
    finally:
        if web is not None:
            web.shutdown()
    return 0
