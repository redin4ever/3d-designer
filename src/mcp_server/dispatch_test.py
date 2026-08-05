"""Tests for ``dispatch`` — role visibility, param validation, the write lock, and result
serialisation for one MCP tool call (ADR-003, ADR-007, Gate A 4.1/4.2).

``dispatch`` is a throwing stub as of this file (Rule 4 — tests come first); every test
below is expected to fail with ``NotImplementedError`` until the next pass implements it.
"""

from __future__ import annotations

import json

import pytest
from contracts import LockContention, Phase, ToolError, ToolRole, WriteLease
from mcp_server import dispatch
from raw import RAW_TOOL_SPEC

_ADD_PRIMITIVE_PARAMS = {"object_id": "box1", "kind": "cube", "size": [1, 1, 1]}


# ------------------------------------------------------------------------- role gating

def test_dispatch_on_a_tool_the_role_cannot_see_raises_tool_error_naming_the_role(
    orchestrator,
) -> None:
    """An EXPORT-role agent has no business reaching a BLOCKOUT construction tool. The
    failure must name *which role* was denied, not surface as a generic lookup miss — an
    agent told the boundary it hit can pick a tool that is actually available to it."""
    with pytest.raises(ToolError) as excinfo:
        dispatch("add_wall", {}, role=ToolRole.EXPORT, orchestrator=orchestrator)
    assert "export" in str(excinfo.value).lower()


def test_dispatch_on_an_unknown_tool_name_also_names_the_role(orchestrator) -> None:
    with pytest.raises(ToolError) as excinfo:
        dispatch("not_a_real_tool", {}, role=ToolRole.BLOCKOUT, orchestrator=orchestrator)
    assert "blockout" in str(excinfo.value).lower()


# --------------------------------------------------------------------- param validation

def test_dispatch_with_a_missing_required_parameter_names_it_and_suggests_a_fix(
    orchestrator, write_lease,
) -> None:
    """An agent handed a bare traceback loops on the same failing call; one told which
    parameter is missing, with a suggestion, fixes it on the first retry (Gate A 4.2)."""
    with pytest.raises(ToolError) as excinfo:
        dispatch(
            "add_primitive", {"object_id": "box1"},
            role=ToolRole.BLOCKOUT, orchestrator=orchestrator, lease=write_lease,
        )
    err = excinfo.value
    assert "kind" in err.detail
    assert err.suggestion


def test_missing_parameter_check_runs_before_the_lock_check(orchestrator) -> None:
    """A caller with no lease yet still deserves to learn its params are wrong first —
    otherwise it acquires a lease, retries, and only then discovers the real problem."""
    with pytest.raises(ToolError) as excinfo:
        dispatch(
            "add_primitive", {"object_id": "box1"},
            role=ToolRole.BLOCKOUT, orchestrator=orchestrator, lease=None,
        )
    assert "kind" in excinfo.value.detail


# ------------------------------------------------------------------------- the write lock

def test_mutating_dispatch_without_a_lease_fails_with_a_lock_error_and_changes_nothing(
    orchestrator, fake_scene,
) -> None:
    with pytest.raises(ToolError) as excinfo:
        dispatch(
            "add_primitive", _ADD_PRIMITIVE_PARAMS,
            role=ToolRole.BLOCKOUT, orchestrator=orchestrator, lease=None,
        )
    message = str(excinfo.value).lower()
    assert "lock" in message or "lease" in message
    assert fake_scene.document().head == 0


def test_mutating_dispatch_with_a_lease_someone_else_holds_raises_lock_contention_and_changes_nothing(
    orchestrator, fake_scene,
) -> None:
    orchestrator.acquire(holder="writer-a", phase=Phase.BLOCKOUT)
    forged = WriteLease(
        holder="writer-b", phase=Phase.BLOCKOUT, lease_id="forged",
        granted_at_op=0, expires_at_op=64,
    )

    with pytest.raises(LockContention):
        dispatch(
            "add_primitive", _ADD_PRIMITIVE_PARAMS,
            role=ToolRole.BLOCKOUT, orchestrator=orchestrator, lease=forged,
        )
    assert fake_scene.document().head == 0


# ------------------------------------------------------------------------ the happy path

def test_a_successful_mutating_dispatch_applies_the_operation_and_returns_a_jsonable_result(
    orchestrator, write_lease, fake_scene,
) -> None:
    result = dispatch(
        "add_primitive", _ADD_PRIMITIVE_PARAMS,
        role=ToolRole.BLOCKOUT, orchestrator=orchestrator, lease=write_lease,
    )

    assert result["ok"] is True
    assert fake_scene.document().head == 1
    json.dumps(result)  # must be real JSON, not just dict-shaped (StrEnum, tuples, ...)


def test_dispatching_raw_execute_records_an_opaque_operation(orchestrator, fake_scene) -> None:
    """ADR-009: every raw call is recorded as an opaque undo barrier — rolling back past
    it needs a snapshot restore, not a replay, and that cost must be visible in the log,
    not silently dropped by the routing layer that dispatches the call."""
    lease = orchestrator.acquire(holder="admin", phase=Phase.BLOCKOUT)

    result = dispatch(
        RAW_TOOL_SPEC.name, {"source": "pass"},
        role=ToolRole.ADMIN, orchestrator=orchestrator, lease=lease,
    )

    assert result["ok"] is True
    logged = fake_scene.document().operations[-1]
    assert logged.opaque is True


def test_dispatch_on_a_read_only_tool_with_no_handler_wired_yet_fails_cleanly(
    orchestrator,
) -> None:
    """``check_export_budget`` is real, registered ``ToolSpec`` content with
    ``handler=None`` (``export/registry.py``'s own docstring: a placeholder ``mcp`` skips
    at registration, not an omission). Calling ``None(...)`` would be a bare
    ``TypeError``; this must instead be a named, honest ``ToolError``."""
    with pytest.raises(ToolError):
        dispatch(
            "check_export_budget", {"object_ids": ["a"]},
            role=ToolRole.EXPORT, orchestrator=orchestrator,
        )
