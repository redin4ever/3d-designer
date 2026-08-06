"""Tests for ``SERVER_INFO`` and the two MCP transports (ADR-003, ADR-009).

These hold transport *policy*: the advertised identity, what happens when the SDK is
absent, where the HTTP transport binds and what it says when that is not loopback. The
SDK-facing wiring is ``sdk_bridge_test.py``'s subject and a live client session is
``live_client_test.py``'s.

**One test here was replaced rather than kept.**
``test_an_sdk_whose_api_this_is_not_written_against_is_refused_by_name`` asserted that the
transports refuse to serve because the installed SDK (2.0.0) lacks the 1.x
``Server.list_tools`` / ``Server.call_tool`` decorators. That refusal was honest and it was
also the defect: nothing could connect over either transport. The transports are now wired
against 2.0's ``on_list_tools`` / ``on_call_tool`` constructor callbacks, so the old
assertion describes a state that must never come back. The knowledge it encoded — *an SDK
this is not written against produces one named sentence, never an ``AttributeError`` or
``TypeError`` from three frames inside someone else's package* — is not lost: it is
``sdk_bridge_test.py::test_an_sdk_without_the_2_0_callback_api_is_refused_by_name``, which
makes the same assertion against the API actually in use.

Each SDK-absence test explicitly rejects ``NotImplementedError`` rather than merely catching
``RuntimeError`` — ``NotImplementedError`` is itself a ``RuntimeError`` subclass, so a bare
``pytest.raises(RuntimeError)`` would have spuriously passed against a throwing stub and
never verified anything. The check is kept: the same trap catches any future stub.
"""

from __future__ import annotations

import logging
import sys

import pytest
from mcp_server import SERVER_INFO, http_app, serve_http, serve_stdio


def _assert_real_runtime_error(excinfo: pytest.ExceptionInfo) -> None:
    """Fail loudly if what was raised is a stub's ``NotImplementedError`` rather than the
    real "SDK not installed" ``RuntimeError`` — see module docstring."""
    assert not isinstance(excinfo.value, NotImplementedError), (
        "caught a stub's NotImplementedError, not a real SDK-missing error"
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


# ------------------------------------------------------------- the SDK is not installed

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


def test_the_registry_and_dispatch_survive_a_missing_sdk(orchestrator, no_sdk) -> None:
    """The reason the SDK import is lazy. Most of this repository's suite runs with no SDK
    at all, and a module-scope import would take the whole decision layer down with it."""
    from mcp_server import build_registry, dispatch

    assert build_registry()
    assert dispatch("get_phase", {}, orchestrator=orchestrator)["phase"]


# --------------------------------------------------------------- ADR-009: where it binds

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
    including raw code execution and full filesystem access, and must never happen
    silently. The warning fires before the SDK is even imported, so an operator who
    mistypes ``--host`` is told even on a machine where the server cannot start."""
    caplog.set_level(logging.WARNING)
    with pytest.raises(RuntimeError) as excinfo:
        serve_http(orchestrator, host="0.0.0.0")
    _assert_real_runtime_error(excinfo)
    assert any("ADR-009" in record.message for record in caplog.records)


# ------------------------------------------------------------- it actually builds an app

def test_http_app_builds_a_real_asgi_app_serving_the_mcp_path(orchestrator) -> None:
    """The streamable-HTTP half of ADR-003 — the path a ChatGPT developer-mode connector
    dials. ``live_client_test.py`` drives stdio end to end; this transport has no client
    available in this environment (``mcp.client.streamable_http`` needs ``httpx``, which is
    not installed), so what is asserted here is that the app is real and routed, not that a
    session completes over it. That gap is stated in ``CLAUDE.md`` rather than papered
    over."""
    pytest.importorskip("mcp.server.lowlevel", reason="the MCP SDK is not installed here")

    app = http_app(orchestrator)

    assert callable(app), "not an ASGI application"
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/mcp" in paths


def test_http_app_returns_a_separately_mountable_app_per_call(orchestrator) -> None:
    """It is a factory, not a singleton: a hosted deployment mounts it inside its own ASGI
    stack behind its own TLS and auth, and two mounts must not share one session manager."""
    pytest.importorskip("mcp.server.lowlevel", reason="the MCP SDK is not installed here")

    assert http_app(orchestrator, path="/a") is not http_app(orchestrator, path="/b")


def test_a_non_loopback_bind_still_builds_rather_than_refusing(orchestrator, caplog) -> None:
    """Gate A 7.2 and 7.4 chose unrestricted execution and unrestricted filesystem access
    with the risk stated in the option text. Refusing a non-loopback bind would be this
    module quietly overriding that; warning loudly and proceeding is the decision the user
    actually made."""
    pytest.importorskip("mcp.server.lowlevel", reason="the MCP SDK is not installed here")
    caplog.set_level(logging.WARNING)

    app = http_app(orchestrator, host="0.0.0.0")

    assert callable(app)
    assert any("ADR-009" in record.message for record in caplog.records)


# ------------------------------------------------------------------ the name collision

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
