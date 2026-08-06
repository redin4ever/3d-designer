"""Tests for ``SERVER_INFO`` and the two MCP transports (ADR-003, ADR-009).

The ``mcp`` SDK **is** installed and importable here (2.0.0) — an earlier version of this
docstring said it was not, and the package-name collision that shadowed it was fixed and is
pinned below. What still cannot be driven end to end is a live client session, so these
tests hold the guarantees that do not need one: the registry and ``dispatch`` stay usable
whatever the SDK's state, ``serve_stdio``/``serve_http`` fail with one clear, named error
rather than a bare ``ModuleNotFoundError`` or an ``AttributeError`` from inside someone
else's package, and ``import mcp`` resolves to the real SDK rather than back to this
package.

Each SDK-absence test explicitly rejects ``NotImplementedError`` rather than merely catching
``RuntimeError`` — ``NotImplementedError`` is itself a ``RuntimeError`` subclass, so a bare
``pytest.raises(RuntimeError)`` would have spuriously passed against the original throwing
stub and never verified anything. The check is kept: the same trap catches any future stub.
"""

from __future__ import annotations

import logging
import sys

import pytest
from mcp_server import SERVER_INFO, serve_http, serve_stdio


def _assert_real_runtime_error(excinfo: pytest.ExceptionInfo) -> None:
    """Fail loudly if what was raised is the throwing stub's ``NotImplementedError``
    rather than the real "SDK not installed" ``RuntimeError`` — see module docstring."""
    assert not isinstance(excinfo.value, NotImplementedError), (
        "caught the throwing stub's NotImplementedError, not a real SDK-missing error"
    )


def test_server_info_names_both_transports() -> None:
    """ADR-003: both stdio (Claude Desktop/Code/Cursor) and streamable HTTP (ChatGPT
    developer-mode connectors) must be advertised — Gate A 7.4's entire point is that a
    consumer subscription can drive this tool, which only works if both are visible."""
    text = " ".join(str(value) for value in SERVER_INFO.values()).lower()
    assert "stdio" in text
    assert "http" in text


@pytest.fixture
def no_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the SDK unimportable for the duration of one test.

    These tests originally just called the transports and relied on the SDK genuinely being
    absent from the machine. That made them assertions about the environment rather than
    about the code, and they inverted the moment the dependency was actually installed —
    passing for the wrong reason before, failing for the wrong reason after. Simulating the
    absence keeps the guarantee under test either way.
    """
    monkeypatch.setitem(sys.modules, "mcp.server", None)


def test_serve_stdio_raises_a_clear_named_error_when_the_sdk_is_not_installed(
    orchestrator, no_sdk,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        serve_stdio(orchestrator)
    _assert_real_runtime_error(excinfo)
    message = str(excinfo.value).lower()
    assert "mcp" in message and "install" in message


def test_serve_http_raises_a_clear_named_error_when_the_sdk_is_not_installed(
    orchestrator, no_sdk,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator)
    _assert_real_runtime_error(excinfo)
    message = str(excinfo.value).lower()
    assert "mcp" in message and "install" in message


def test_serve_http_on_the_default_loopback_host_logs_no_adr_009_warning(
    orchestrator, caplog, no_sdk,
) -> None:
    caplog.set_level(logging.WARNING)
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator)  # SDK missing still raises — no warning should precede it
    _assert_real_runtime_error(excinfo)
    assert not any("ADR-009" in record.message for record in caplog.records)


def test_serve_http_on_a_non_loopback_host_logs_a_warning_naming_adr_009(
    orchestrator, caplog, no_sdk,
) -> None:
    """ADR-009: the HTTP transport binds loopback by default; binding to a non-loopback
    address is a real, unauthenticated network surface reaching every registered tool,
    including raw code execution, and must never happen silently."""
    caplog.set_level(logging.WARNING)
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator, host="0.0.0.0")
    _assert_real_runtime_error(excinfo)
    assert any("ADR-009" in record.message for record in caplog.records)


def test_an_sdk_whose_api_this_is_not_written_against_is_refused_by_name(
    orchestrator,
) -> None:
    """The SDK installed here is 2.0.0, whose ``mcp.server.Server`` no longer carries the
    ``list_tools``/``call_tool`` decorators this module wires against (they were 1.x). An
    operator who runs the server gets one sentence naming the installed version and what
    it offers instead — not an ``AttributeError`` three frames inside someone else's
    package, which tells them nothing about which side is wrong."""
    with pytest.raises(RuntimeError) as excinfo:
        serve_stdio(orchestrator)
    _assert_real_runtime_error(excinfo)
    assert not isinstance(excinfo.value, AttributeError)
    message = str(excinfo.value)
    assert "mcp" in message.lower()
    assert "MCPServer" in message or "install" in message


def test_the_sdk_resolves_to_the_real_package_not_this_one() -> None:
    """This package used to be named ``mcp``, so ``import mcp`` from inside it resolved
    back to itself and the SDK was permanently unreachable — meaning no subscription
    client could ever have connected, which is the one thing Gate A 7.4 asked for. If the
    rename is ever undone, this catches it immediately rather than at a customer's first
    connection attempt."""
    pytest.importorskip("mcp.server", reason="SDK not installed here")
    import mcp

    assert not (mcp.__file__ or "").replace("\\", "/").endswith("src/mcp_server/__init__.py")
    assert "mcp_server" not in (mcp.__file__ or ""), (
        "`import mcp` resolved to this package — the SDK is shadowed and unreachable"
    )
