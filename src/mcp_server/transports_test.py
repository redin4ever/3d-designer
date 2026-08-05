"""Tests for ``SERVER_INFO`` and the two MCP transports (ADR-003, ADR-009).

Neither transport can be driven end to end here — the ``mcp`` Python SDK is not installed
in this environment (see ``CLAUDE.md``) — so these tests hold the two guarantees the
module brief actually requires: the registry/``dispatch`` stay usable without it, and
``serve_stdio``/``serve_http`` fail with one clear, named error instead of a bare
``ModuleNotFoundError`` surfacing from inside someone else's package. The ADR-009
loopback-by-default warning is fully testable without the SDK, since it runs before the
SDK is ever imported.

``serve_stdio``/``serve_http`` are throwing stubs as of this file (Rule 4 — tests come
first); the SDK-absence and warning tests below are expected to fail until the next pass
implements them. Each explicitly rejects ``NotImplementedError`` rather than merely
catching ``RuntimeError`` — ``NotImplementedError`` is itself a ``RuntimeError``
subclass, so a bare ``pytest.raises(RuntimeError)`` would spuriously pass against the
throwing stub and never actually verify anything (the stub's own message even contains
the word "mcp"). ``SERVER_INFO`` is real, already-constructed data — its test passes now.
"""

from __future__ import annotations

import logging

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


def test_serve_stdio_raises_a_clear_named_error_when_the_sdk_is_not_installed(
    orchestrator,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        serve_stdio(orchestrator)
    _assert_real_runtime_error(excinfo)
    message = str(excinfo.value).lower()
    assert "mcp" in message and "install" in message


def test_serve_http_raises_a_clear_named_error_when_the_sdk_is_not_installed(
    orchestrator,
) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator)
    _assert_real_runtime_error(excinfo)
    message = str(excinfo.value).lower()
    assert "mcp" in message and "install" in message


def test_serve_http_on_the_default_loopback_host_logs_no_adr_009_warning(
    orchestrator, caplog,
) -> None:
    caplog.set_level(logging.WARNING)
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator)  # SDK missing still raises — no warning should precede it
    _assert_real_runtime_error(excinfo)
    assert not any("ADR-009" in record.message for record in caplog.records)


def test_serve_http_on_a_non_loopback_host_logs_a_warning_naming_adr_009(
    orchestrator, caplog,
) -> None:
    """ADR-009: the HTTP transport binds loopback by default; binding to a non-loopback
    address is a real, unauthenticated network surface reaching every registered tool,
    including raw code execution, and must never happen silently."""
    caplog.set_level(logging.WARNING)
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator, host="0.0.0.0")
    _assert_real_runtime_error(excinfo)
    assert any("ADR-009" in record.message for record in caplog.records)
