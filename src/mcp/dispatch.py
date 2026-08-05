"""``dispatch`` — route one MCP tool call end to end: role visibility, param validation,
the write lock for mutating calls, execution, and a JSON-serialisable result (ADR-003,
ADR-007, Gate A 4.1/4.2).

Nothing here computes anything yet — every function raises until the next pass replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

import uuid
from typing import Any

from contracts import Operation, ToolError, ToolRole, ToolSpec
from raw import RAW_TOOL_SPEC

from .registry import tools_for
from .serialize import to_jsonable
from .validation import validate_params

__all__ = ["dispatch"]


def _find_spec(name: str, role: ToolRole) -> ToolSpec:
    for spec in tools_for(role):
        if spec.name == name:
            return spec
    visible = ", ".join(spec.name for spec in tools_for(role)) or "(none)"
    raise ToolError(
        rule="mcp.tool_not_visible",
        detail=f"tool {name!r} is not visible to role {role.value!r}",
        suggestion=f"role {role.value!r} can call: {visible}",
    )


def dispatch(
    name: str,
    params: dict[str, Any],
    *,
    role: ToolRole,
    orchestrator: Any,
    lease: Any = None,
) -> dict[str, Any]:
    """Look up ``name`` in ``role``'s visible tools, validate ``params`` against its
    schema, take the write lock for a mutating tool, execute, and return a
    JSON-serialisable result.

    - A tool ``name`` not in ``tools_for(role)`` raises :class:`contracts.ToolError`
      naming ``role`` — never a generic lookup failure.
    - A missing required parameter raises :class:`contracts.ToolError` naming that
      parameter and carrying a ``suggestion``, checked before the write lock — a caller
      with no lease yet still deserves to learn its params are wrong first.
    - A mutating tool called with ``lease=None`` raises :class:`contracts.ToolError`
      before anything is touched; called with a lease that is not the live one, it lets
      :class:`contracts.LockContention` propagate from ``orchestrator.verify`` — both are
      "a lock error", neither changes the scene.
    - A mutating tool with a directly-registered ``ToolSpec.handler`` calls it once the
      lock is verified. Every current ``ToolSpec`` in this codebase has ``handler=None``
      (registry *content* deliberately leaves execution to the log — see
      ``export/registry.py``'s own docstring), so the live path today builds a
      :class:`contracts.Operation` named after the tool and runs it through
      ``orchestrator.perform`` — the log ADR-002 already keeps, not a second execution
      path invented here. ``raw_execute`` specifically is marked ``opaque=True`` (ADR-009:
      every raw call is an undo barrier).
    - A non-mutating tool with no handler raises :class:`contracts.ToolError` rather than
      calling ``None(...)`` — an honest "not wired up yet", never a bare ``TypeError``.
    """
    spec = _find_spec(name, role)
    validate_params(name, spec.input_schema, params)

    if not spec.mutating:
        if spec.handler is None:
            raise ToolError(
                rule="mcp.handler_not_wired",
                detail=f"{name!r} has no handler registered yet",
                suggestion="this tool's implementation is not available through mcp yet",
            )
        return to_jsonable(spec.handler(**params))

    if lease is None:
        raise ToolError(
            rule="mcp.lock_required",
            detail=f"{name!r} mutates the scene and requires a write lease; none was given",
            suggestion="acquire one with orchestrator.acquire(holder, phase) first",
        )

    orchestrator.verify(lease)  # raises contracts.LockContention if lease is not the live one

    if spec.handler is not None:
        return to_jsonable(spec.handler(**params))

    op = Operation(
        op_id=f"{name}-{uuid.uuid4().hex[:8]}",
        kind=name,
        params=dict(params),
        phase=orchestrator.phase.value,
        author=f"mcp:{role.value}",
        opaque=(name == RAW_TOOL_SPEC.name),
    )
    report = orchestrator.perform(op, lease)
    return to_jsonable(report)
