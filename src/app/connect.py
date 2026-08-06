"""``forge3d connect`` — the exact configuration each AI client needs, with real paths.

Gate A 7.4, in the user's own words: *"make sure it supports my subscriptions eg: chatgpt
subscription so that i can use it with it"*. The server that makes that possible works and
is tested against a real client. What was missing was the last step — knowing what to paste
where — and that step is where a working MCP server usually dies, because the config is a
JSON file in a per-app location with absolute paths that differ on every machine.

So this prints the config with **this** machine's interpreter and **this** checkout already
filled in, and can write it into the client's own file.

The honest part matters as much as the config. The two clients are not equally reachable:

* **Claude Desktop, Claude Code and Cursor** speak MCP over **stdio** — they launch the
  server as a subprocess. Localhost is not involved, nothing is exposed, and it works as
  soon as the config is saved.

* **ChatGPT** connectors speak MCP over **streamable HTTP**, and ChatGPT's servers make the
  request — not the browser on this machine. A `127.0.0.1` URL is unreachable to them by
  definition, so this cannot be made to work by configuration alone: it needs a public
  HTTPS address pointing at this machine.

  That is a genuine security decision, not a setup step, and it is why this command
  refuses to print a tunnel command as though it were routine. ADR-009 and Gate A 7.2 give
  every connected agent **arbitrary code execution and unrestricted filesystem access**, by
  explicit choice, on the machine this runs on. Behind loopback the trust boundary is this
  computer. Behind a public tunnel it is whoever finds the URL.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

__all__ = ["CLIENTS", "config_for", "config_path_for", "describe", "write_config"]

_SRC = Path(__file__).resolve().parents[1]
_REPO = _SRC.parent


def _server_command() -> dict:
    """The stdio launch command, with this machine's interpreter and checkout.

    ``-X utf8`` because this text crosses a Windows console that defaults to cp1252 and the
    tool's own output is full of em dashes; ``PYTHONPATH`` explicitly because a client
    launches the server with a small, sanitised environment and an inherited one would make
    this work or not depending on how the client itself was started.
    """
    return {
        "command": sys.executable,
        "args": ["-X", "utf8", "-m", "mcp_server"],
        "env": {"PYTHONPATH": str(_SRC), "PYTHONIOENCODING": "utf-8"},
    }


CLIENTS: dict[str, dict] = {
    "claude-desktop": {
        "label": "Claude Desktop",
        "transport": "stdio",
        "path": lambda: (
            Path(os.environ.get("APPDATA", Path.home())) / "Claude" / "claude_desktop_config.json"
            if sys.platform == "win32"
            else Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        ),
        "wrap": lambda cmd: {"mcpServers": {"forge3d": cmd}},
        "note": "Restart Claude Desktop after saving. forge3d appears under the tools icon.",
    },
    "claude-code": {
        "label": "Claude Code",
        "transport": "stdio",
        "path": lambda: Path.home() / ".claude.json",
        "wrap": lambda cmd: {"mcpServers": {"forge3d": cmd}},
        "note": "Or run:  claude mcp add forge3d -- "
                + sys.executable + " -X utf8 -m mcp_server",
    },
    "cursor": {
        "label": "Cursor",
        "transport": "stdio",
        "path": lambda: Path.home() / ".cursor" / "mcp.json",
        "wrap": lambda cmd: {"mcpServers": {"forge3d": cmd}},
        "note": "Settings -> MCP shows it once the file is saved.",
    },
}


def _looks_installed(client: str) -> bool:
    """Whether this client appears to be on this machine.

    Detected by its **config location**, not by hunting for an executable. A client that
    has ever run has written its config directory; an installed-but-never-launched one has
    not, and offering to configure something that will overwrite the file on first launch
    is worse than not offering.

    Deliberately generous: the directory existing is enough. A false positive costs a
    config file in a folder the client already owns, and a false negative hides the whole
    feature from someone who does have the client — so the failure modes are not
    symmetric, and this errs toward showing it.
    """
    path = config_path_for(client)
    return path.exists() or path.parent.exists()


def _already_configured(client: str) -> bool:
    path = config_path_for(client)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return False
    return "forge3d" in (data.get("mcpServers") or {})


def detect_clients() -> list[dict]:
    """Every AI client on this machine that forge3d can wire itself into.

    Returned rather than printed, so the browser's Connect button and the CLI can share one
    answer instead of drifting apart.
    """
    found = []
    for name, spec in CLIENTS.items():
        if not _looks_installed(name):
            continue
        found.append(
            {
                "id": name,
                "label": spec["label"],
                "transport": spec["transport"],
                "config_path": str(config_path_for(name)),
                "configured": _already_configured(name),
                "note": spec["note"],
            }
        )
    return found


def config_for(client: str) -> dict:
    """The JSON this client expects, ready to paste."""
    if client not in CLIENTS:
        raise KeyError(f"unknown client {client!r}; known: {', '.join(sorted(CLIENTS))}")
    return CLIENTS[client]["wrap"](_server_command())


def config_path_for(client: str) -> Path:
    return CLIENTS[client]["path"]()


def write_config(client: str) -> Path:
    """Merge forge3d into the client's existing config, and return the path.

    Merged, never overwritten: these files hold every other MCP server the person has set
    up, and replacing one to add ours would silently disconnect all of them. An unreadable
    or malformed existing file is left alone and reported rather than clobbered.
    """
    path = config_path_for(client)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"{path} exists but could not be read as JSON ({exc}). Left untouched — "
                "fix or move it, then run this again."
            ) from exc

    servers = dict(existing.get("mcpServers") or {})
    servers["forge3d"] = _server_command()
    merged = {**existing, "mcpServers": servers}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return path


def describe(client: str | None = None, *, http_port: int = 8765) -> str:
    """The whole answer to "how do I connect my AI to this", as text."""
    lines: list[str] = []

    # "chatgpt" is a real client name and not a stdio one — it falls through to the HTTP
    # section below rather than being looked up here, and asking for it by name must not
    # read as a typo.
    wanted = [client] if client and client != "chatgpt" else ([] if client else list(CLIENTS))
    for name in wanted:
        if name not in CLIENTS:
            known = ", ".join(sorted(CLIENTS))
            return f"  Unknown client {name!r}. Known: {known}, chatgpt"
        spec = CLIENTS[name]
        lines.append(f"\n  {spec['label']}  ({spec['transport']})")
        lines.append(f"  config: {config_path_for(name)}")
        lines.append("")
        for row in json.dumps(config_for(name), indent=2).splitlines():
            lines.append(f"    {row}")
        lines.append("")
        lines.append(f"  {spec['note']}")

    if client in (None, "chatgpt"):
        lines.append("")
        lines.append("  ChatGPT  (streamable HTTP)")
        lines.append(f"  forge3d run  serves MCP at  http://127.0.0.1:{http_port}/mcp")
        lines.append("")
        lines.append("  This one does not work by configuration alone, and it is worth")
        lines.append("  knowing why before you go looking for a workaround: ChatGPT's own")
        lines.append("  servers make the request, not the browser on this machine, so a")
        lines.append("  127.0.0.1 address is unreachable to them. It needs a public HTTPS")
        lines.append("  URL pointing here.")
        lines.append("")
        lines.append("  That is a security decision, not a setup step. Every connected")
        lines.append("  agent gets arbitrary code execution and full filesystem access on")
        lines.append("  this machine, by your own choice at Gate A 7.2 (ADR-009). Behind")
        lines.append("  loopback the trust boundary is this computer. Behind a public")
        lines.append("  tunnel it is whoever finds the URL — so if you do tunnel it, treat")
        lines.append("  the address as a credential and take it down afterwards.")

    return "\n".join(lines)
