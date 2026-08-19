"""Preserving reads and writes for Codex's native ``config.toml`` MCP tables.

Python's standard library reads TOML but deliberately does not write it. Re-serialising a
Codex config through a generic writer would also erase comments and ordering in a file that
contains far more than MCP settings. This module therefore validates the whole document,
replaces only forge3d's ordinary tables, and leaves every unrelated byte alone.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_TABLE = re.compile(r"^\s*\[([^\[\]]+)]\s*(?:#.*)?$")


def _string(value: str) -> str:
    """A TOML basic string, using the JSON escaping both formats share."""
    return json.dumps(value, ensure_ascii=False)


def format_server(command: dict) -> str:
    """Render one native Codex stdio MCP server table."""
    args = ", ".join(_string(str(value)) for value in command.get("args", []))
    lines = [
        "[mcp_servers.forge3d]",
        f"command = {_string(str(command['command']))}",
        f"args = [{args}]",
    ]
    env = command.get("env") or {}
    if env:
        lines.extend(["", "[mcp_servers.forge3d.env]"])
        lines.extend(f"{key} = {_string(str(value))}" for key, value in env.items())
    return "\n".join(lines) + "\n"


def _without_server(text: str) -> tuple[str, bool]:
    """Remove only forge3d's ordinary TOML tables, preserving every other byte."""
    lines = text.splitlines(keepends=True)
    headers: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = _TABLE.match(line.rstrip("\r\n"))
        if match:
            headers.append((index, match.group(1).strip()))

    remove = [False] * len(lines)
    found = False
    for position, (start, name) in enumerate(headers):
        if name != "mcp_servers.forge3d" and not name.startswith("mcp_servers.forge3d."):
            continue
        found = True
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        for index in range(start, end):
            remove[index] = True
    return "".join(line for index, line in enumerate(lines) if not remove[index]), found


def write_server(path: Path, command: dict) -> None:
    """Merge forge3d into Codex TOML without reserialising unrelated user settings."""
    text = ""
    parsed: dict = {}
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            parsed = tomllib.loads(text)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(
                f"{path} exists but could not be read as TOML ({exc}). Left untouched — "
                "fix or move it, then run this again."
            ) from exc

    kept, removed = _without_server(text)
    already_present = "forge3d" in (parsed.get("mcp_servers") or {})
    if already_present and not removed:
        raise RuntimeError(
            f"{path} defines mcp_servers.forge3d in an unsupported inline TOML shape. "
            "Left untouched — remove that entry, then run this again."
        )

    prefix = kept.rstrip()
    merged = (prefix + "\n\n" if prefix else "") + format_server(command)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged, encoding="utf-8")
