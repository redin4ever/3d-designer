"""`forge3d connect` — the last step, which is where a working MCP server usually dies.

Gate A 7.4, verbatim: "make sure it supports my subscriptions eg: chatgpt subscription so
that i can use it with it". The server works and is tested against a real client; what was
missing was knowing what to paste where, with absolute paths that differ per machine.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

from app.connect import CLIENTS, config_for, config_path_for, describe, write_config


def _command_for(client: str) -> dict:
    config = config_for(client)
    servers = config["mcp_servers"] if client == "codex" else config["mcpServers"]
    return servers["forge3d"]


@pytest.mark.parametrize("client", sorted(CLIENTS))
def test_the_config_launches_this_interpreter_not_whatever_is_on_path(client: str) -> None:
    """`python` on PATH here is the Windows Store alias stub and runs nothing. A config
    naming it produces a client that reports the server as failed to start, with no clue."""
    cmd = _command_for(client)
    assert cmd["command"] == sys.executable


@pytest.mark.parametrize("client", sorted(CLIENTS))
def test_the_config_sets_pythonpath_rather_than_inheriting_it(client: str) -> None:
    """A client launches the server with a small, sanitised environment. Relying on an
    inherited PYTHONPATH makes it work or not depending on how the client itself was
    started, which is the worst kind of intermittent."""
    cmd = _command_for(client)
    assert cmd["env"]["PYTHONPATH"].endswith("src")


@pytest.mark.parametrize("client", sorted(CLIENTS))
def test_the_config_forces_utf8(client: str) -> None:
    """This tool's errors, defect reports and export banners are full of em dashes, and a
    Windows console is cp1252. Without this the first clipping defect kills the server."""
    cmd = _command_for(client)
    assert "-X" in cmd["args"] and "utf8" in cmd["args"]
    assert cmd["env"]["PYTHONIOENCODING"] == "utf-8"


def test_writing_merges_rather_than_replacing(tmp_path, monkeypatch) -> None:
    """These files hold every other MCP server the person has set up. Replacing one to add
    ours would silently disconnect all of them."""
    target = tmp_path / "claude_desktop_config.json"
    target.write_text(
        json.dumps({"mcpServers": {"other": {"command": "keep-me"}}, "theme": "dark"}),
        encoding="utf-8",
    )
    monkeypatch.setitem(CLIENTS["claude-desktop"], "path", lambda: target)

    write_config("claude-desktop")

    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["mcpServers"]["other"]["command"] == "keep-me", "clobbered another server"
    assert "forge3d" in written["mcpServers"]
    assert written["theme"] == "dark", "dropped an unrelated setting"


def test_an_unreadable_config_is_reported_not_clobbered(tmp_path, monkeypatch) -> None:
    """Overwriting a file we could not parse would destroy a setup we cannot see."""
    target = tmp_path / "broken.json"
    target.write_text("{ not json at all", encoding="utf-8")
    monkeypatch.setitem(CLIENTS["claude-desktop"], "path", lambda: target)

    with pytest.raises(RuntimeError, match="could not be read"):
        write_config("claude-desktop")

    assert target.read_text(encoding="utf-8") == "{ not json at all"


def test_writing_creates_the_directory_when_the_client_has_never_run(tmp_path, monkeypatch) -> None:
    target = tmp_path / "never" / "existed" / "config.json"
    monkeypatch.setitem(CLIENTS["cursor"], "path", lambda: target)

    write_config("cursor")

    assert json.loads(target.read_text(encoding="utf-8"))["mcpServers"]["forge3d"]


def test_codex_is_one_global_toml_client_shared_by_its_local_surfaces() -> None:
    """Codex CLI, the IDE extension and ChatGPT desktop share one host configuration.
    Offering three picker rows would let the same file be written three indistinguishable
    ways, while using a project file would make Connect mysteriously vanish elsewhere."""
    assert CLIENTS["codex"]["label"] == "Codex"
    assert config_path_for("codex") == Path.home() / ".codex" / "config.toml"
    assert _command_for("codex")["command"] == sys.executable


def test_writing_codex_merges_parseable_toml_without_erasing_comments(tmp_path, monkeypatch) -> None:
    """Codex's config is TOML, not the JSON every existing client uses. The button must
    preserve unrelated settings and comments because this file controls far more than MCP."""
    target = tmp_path / ".codex" / "config.toml"
    target.parent.mkdir()
    target.write_text(
        "# keep this operator note\nmodel = \"gpt-5\"\n\n[mcp_servers.other]\ncommand = \"keep-me\"\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(CLIENTS["codex"], "path", lambda: target)

    write_config("codex")
    write_config("codex")

    text = target.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert "# keep this operator note" in text
    assert parsed["model"] == "gpt-5"
    assert parsed["mcp_servers"]["other"]["command"] == "keep-me"
    assert parsed["mcp_servers"]["forge3d"]["command"] == sys.executable
    assert parsed["mcp_servers"]["forge3d"]["env"]["PYTHONPATH"].endswith("src")
    assert text.count("[mcp_servers.forge3d]") == 1, "reconnect duplicated the server table"


def test_malformed_codex_toml_is_reported_and_left_untouched(tmp_path, monkeypatch) -> None:
    target = tmp_path / "config.toml"
    broken = "[mcp_servers.forge3d\ncommand = nope"
    target.write_text(broken, encoding="utf-8")
    monkeypatch.setitem(CLIENTS["codex"], "path", lambda: target)

    with pytest.raises(RuntimeError, match="TOML"):
        write_config("codex")

    assert target.read_text(encoding="utf-8") == broken


def test_describe_codex_prints_toml_not_a_json_mcpservers_object() -> None:
    text = describe("codex")
    assert "Unknown client" not in text
    assert "[mcp_servers.forge3d]" in text
    assert "mcpServers" not in text
    assert "config.toml" in text


def test_chatgpt_is_a_known_client_and_says_why_localhost_cannot_work() -> None:
    """Asking for it by name must not read as a typo, and the answer must be the real one:
    ChatGPT's servers make the request, so 127.0.0.1 is unreachable to them by definition.
    A person who does not learn that goes looking for a config option that cannot exist."""
    text = describe("chatgpt")
    assert "Unknown client" not in text
    assert "127.0.0.1" in text
    assert "HTTPS" in text


def test_the_chatgpt_route_states_the_exposure_rather_than_just_the_recipe() -> None:
    """ADR-009 gives every connected agent arbitrary code execution and full filesystem
    access on this machine. Handing someone a tunnel command without saying that is how a
    deliberate local-trust decision becomes an accidental public one."""
    text = describe("chatgpt")
    assert "ADR-009" in text
    assert "arbitrary code execution" in text


def test_every_client_names_a_real_config_path() -> None:
    for client in CLIENTS:
        suffix = ".toml" if client == "codex" else ".json"
        assert config_path_for(client).name.endswith(suffix)
