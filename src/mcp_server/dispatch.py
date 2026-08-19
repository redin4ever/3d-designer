"""``dispatch`` — route one MCP tool call end to end: parameter validation, role-and-phase
authorisation, the write lock for mutating calls, execution, and a JSON-serialisable
result (ADR-003, ADR-007, ADR-013, ADR-014, Gate A 4.1/4.2).
"""

from __future__ import annotations

import uuid
from typing import Any

from contracts import Operation, Phase, ToolError, ToolRole, ToolSpec, roles_for_phase
from raw import RAW_TOOL_SPEC
from importing import IMPORT_OPERATION_KIND

from .authorize import authorize
from .context import context_for
from .registry import tools_for
from .serialize import to_jsonable
from .validation import validate_params

__all__ = ["dispatch"]


def _callable_now(phase: Phase) -> list[str]:
    return sorted({spec.name for role in roles_for_phase(phase) for spec in tools_for(role)})


def _find_spec(name: str, phase: Phase) -> ToolSpec:
    """Look ``name`` up across the whole registry, not inside one role's slice.

    Which role may call it is :mod:`mcp_server.authorize`'s decision, made from the lease
    (ADR-013) — so a tool that exists but is not available yet must produce a *phase*
    refusal that says when it becomes available, never "no such tool". Those are different
    problems and an agent handed the wrong one changes the wrong thing.

    The refusal lists what is callable in this phase, not the whole catalogue: an agent that
    misnamed a tool needs the shortlist it should have chosen from, and at the stated scale
    the full list is neither short nor relevant.
    """
    for role in ToolRole:
        for spec in tools_for(role):
            if spec.name == name:
                return spec
    raise ToolError(
        rule="mcp.unknown_tool",
        detail=f"no tool named {name!r} is registered",
        suggestion=(
            f"tools callable in phase {phase.value!r}: {', '.join(_callable_now(phase))}"
        ),
    )


def _run(spec: ToolSpec, params: dict[str, Any], orchestrator: Any) -> dict[str, Any]:
    """Call a tool's own handler, supplying whatever live context it declared."""
    if spec.handler is None:
        raise ToolError(
            rule="mcp.handler_not_wired",
            detail=f"{spec.name!r} is registered but has no handler behind it",
            suggestion=(
                f"{spec.name!r} is declared in the registry and not implemented yet — pick "
                "another tool for now; this is a gap in the product, not in your call"
            ),
        )
    return to_jsonable(spec.handler(**context_for(spec.handler, orchestrator), **params))


def dispatch(
    name: str,
    params: dict[str, Any],
    *,
    role: ToolRole | None = None,
    orchestrator: Any,
    lease: Any = None,
) -> dict[str, Any]:
    """Validate ``params``, check what the caller may do, take the write lock for a
    mutating tool, execute, and return a JSON-serialisable result.

    ``role`` is **accepted and ignored** (ADR-013). It used to be the only thing consulted:
    ``dispatch`` checked that the requested tool was visible to the role string the caller
    passed, and never compared it to the session's phase — so any agent could hold any role
    by naming it, and ``unwrap_uvs`` ran in a session that had never left ``blockout``. The
    role now comes from the lease the lock manager issued. The parameter stays in the
    signature rather than being deleted because several callers outside this module's write
    boundary pass it (Rule 5), and a keyword that is ignored is a smaller change to reverse
    than one that raises; it is a candidate for removal in a later reconciliation round.

    The order of checks is deliberate:

    1. **Find the tool** anywhere in the registry. A tool that exists but is not legal yet
       gets a phase refusal, never "no such tool".
    2. **Validate parameters**, before anything about locks or roles. A caller with no lease
       yet still deserves to learn its params are wrong first, rather than acquiring one,
       retrying, and only then discovering the real problem
       (``dispatch_test.py::test_missing_parameter_check_runs_before_the_lock_check``).
    3. **Require a lease for a mutating tool** — reported as a lock error, which is what it
       is, rather than as a role refusal.
    4. **Authorise against the phase and the lease** (:mod:`mcp_server.authorize`). This is
       a coordination mechanism, not a security boundary: ADR-009 gives every connected
       agent arbitrary code execution by explicit user choice, and no role check contains
       that.
    5. **Execute.** A read-only tool runs with no write lock at all — that is what lets many
       INSPECT agents run beside the one writer (ADR-007). A mutating tool verifies the
       lease first (``contracts.LockContention`` propagates from ``orchestrator.verify``),
       then either calls its own handler — export, which writes a file and produces no
       geometry, so it stays out of the operation log entirely (ADR-014) — or builds a
       :class:`contracts.Operation` named after the tool and runs it through
       ``orchestrator.perform``, the log ADR-002 already keeps. ``raw_execute`` is marked
       ``opaque=True`` (ADR-009: every raw call is an undo barrier).
    """
    phase: Phase = orchestrator.phase
    spec = _find_spec(name, phase)
    validate_params(name, spec.input_schema, params)

    if spec.mutating and lease is None:
        raise ToolError(
            rule="mcp.lock_required",
            detail=f"{name!r} mutates the scene and requires a write lease; none was given",
            suggestion=(
                "acquire one with orchestrator.acquire(holder, phase) first, or use a "
                "read-only tool (get_phase, list_objects, describe_object), which needs no "
                "lease and may run concurrently"
            ),
        )

    granted = authorize(spec, orchestrator=orchestrator, lease=lease)

    if not spec.mutating:
        return _run(spec, params, orchestrator)

    orchestrator.verify(lease)  # raises contracts.LockContention if lease is not the live one

    if spec.handler is not None:
        return _run(spec, params, orchestrator)

    # Attribution is role *and* holder: conflict detection compares authors, and after
    # ADR-013 the role is no longer a per-agent identity — several agents can hold the same
    # one. `granted` cannot normally be empty here (authorize only returns after a match),
    # so the fallback is belt-and-braces rather than an expected path.
    acting_role = granted[0].value if granted else spec.roles[0].value
    op_id = f"{name}-{uuid.uuid4().hex[:8]}"
    from ops import joinery_for, runtime_acceptance_for

    op = Operation(
        op_id=op_id,
        kind=name,
        params=dict(params),
        acceptance=runtime_acceptance_for(name, params, op_id=op_id),
        joinery=joinery_for(name, params),
        phase=phase.value,
        author=f"mcp:{acting_role}:{getattr(lease, 'holder', '')}",
        opaque=(name in {RAW_TOOL_SPEC.name, IMPORT_OPERATION_KIND}),
    )
    report = orchestrator.perform(op, lease)
    return to_jsonable(report)
