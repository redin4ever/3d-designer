"""``get_phase`` and ``promote_phase`` — how an agent finds out where it is and moves on
(Gate B 3.1, ADR-012, ADR-013).

Until Gate B there was no way for a connected agent to ask what phase it was in, and no way
to advance one. Gate A 4.4 chose a fully autonomous run; against that registry an
autonomous run could build forever and never promote, never export and never finish. These
two tools are the missing control surface, and after ADR-013 they are also the only way to
find out what the phase gate will now accept.

**There is no force parameter and there must never be one.** ADR-012 removed the promotion
override at Gate B 1.1 because what shipped before it promoted whenever the phase had
recorded any operation at all — the acceptance queries were declared and never evaluated.
Re-introducing the override as a tool parameter would restore exactly that, through a door
the ADR did not think to close. The consequence is that a refusal has to be *actionable*:
with no override left, the failing query is the instruction.

Not part of ``mcp_server``'s public barrel — reached through the registry and ``dispatch``.
"""

from __future__ import annotations

from typing import Any

from contracts import PHASE_ORDER, AcceptanceResult, ToolError, roles_for_phase

from .context import needs

__all__ = ["get_phase", "promote_phase"]


def _line(result: AcceptanceResult) -> str:
    """One failing query, rendered so an agent can act on it: subject, measured value,
    threshold, and the operation that would fix it.

    ASCII only, deliberately. ``AcceptanceResult.describe`` renders an arrow and an em dash;
    this text travels into exception messages, log files and a Windows console whose default
    encoding is cp1252, where a non-ASCII character raises ``UnicodeEncodeError`` and takes
    the whole call down — the same reason ``contracts.Defect.describe`` spells its
    intersection sign ``x``.
    """
    parts = [f"FAIL {result.query_id}"]
    if result.subject:
        parts.append(f"on {result.subject}")
    if result.actual is not None and result.expected is not None:
        parts.append(f"measured {result.actual:.6g}, needs {result.expected:.6g}")
    elif result.actual is not None:
        parts.append(f"measured {result.actual:.6g}")
    if result.reason:
        parts.append(f"- {result.reason}")
    if result.suggested_operation:
        parts.append(f"- try {result.suggested_operation}")
    return " ".join(parts)


def _render(result: AcceptanceResult) -> dict[str, Any]:
    """Every field an agent needs, always present — ``None`` where a query genuinely has no
    value, never omitted. A key that appears only sometimes is one a caller writes code
    against and then crashes on the first query that lacks it."""
    return {
        "query_id": result.query_id,
        "passed": result.passed,
        "subject": result.subject,
        "actual": result.actual,
        "expected": result.expected,
        "reason": result.reason,
        "suggested_operation": result.suggested_operation,
        "describe": _line(result) if not result.passed else f"PASS {result.query_id}",
    }


def _acceptance(orchestrator: Any) -> tuple[bool, tuple[AcceptanceResult, ...]]:
    """``Orchestrator.can_promote()``, or an honest failure standing in for it.

    A crash here would otherwise turn "the gate could not be evaluated" into "there is no
    gate", which is the one direction this must never fail in — a promotion granted because
    the check itself broke is exactly what ADR-012 exists to prevent.
    """
    try:
        can, results = orchestrator.can_promote()
        return bool(can), tuple(results)
    except Exception as exc:  # noqa: BLE001 — an unevaluable gate is a closed gate
        return False, (
            AcceptanceResult(
                query_id="orchestration.can_promote_failed",
                passed=False,
                reason=f"the phase gate could not be evaluated: {type(exc).__name__}: {exc}",
                suggested_operation="get_phase() again after fixing the scene, or raw_execute to inspect",
            ),
        )


def _tools_callable_in(phase) -> list[str]:
    from .registry import tools_for

    return sorted(
        {spec.name for role in roles_for_phase(phase) for spec in tools_for(role)}
    )


@needs("orchestrator")
def get_phase(*, orchestrator: Any) -> dict[str, Any]:
    """Where the session is, what it may call, and what stands between it and the next
    phase."""
    phase = orchestrator.phase
    can, results = _acceptance(orchestrator)
    failing = [r for r in results if not r.passed]
    index = PHASE_ORDER.index(phase)
    next_phase = PHASE_ORDER[index + 1].value if index + 1 < len(PHASE_ORDER) else None

    if can and next_phase:
        summary = f"phase {phase.value}: every acceptance query passes — call promote_phase to reach {next_phase}"
    elif can:
        summary = f"phase {phase.value}: every acceptance query passes; this is the last phase"
    else:
        summary = (
            f"phase {phase.value}: {len(failing)} acceptance query/queries failing — "
            "fix these before promote_phase will advance"
        )

    from .registry import focused_tools

    operator_focus = list(getattr(orchestrator, "focus", ()) or ())
    annotation_images = list(
        getattr(orchestrator, "held_annotation_images", lambda: ())() or ()
    )
    next_actions: list[str] = []
    if operator_focus or annotation_images:
        next_actions.append(
            "Review get_operator_context before changing the operator's focused area."
        )
    for result in failing:
        if result.suggested_operation and result.suggested_operation not in next_actions:
            next_actions.append(result.suggested_operation)
    next_actions.append(
        "Inspect affected objects and measure critical dimensions, angles, gaps, clipping, "
        "and defects before declaring this pass complete."
    )
    if can and next_phase:
        next_actions.append("Call promote_phase only after the final visual and measured check.")
    elif can:
        next_actions.append("Switch focus to export and run the export budget check.")

    return {
        "phase": phase.value,
        "next_phase": next_phase,
        "roles_legal_now": sorted(role.value for role in roles_for_phase(phase)),
        "tools_callable_now": _tools_callable_in(phase),
        "focused_tools": sorted(spec.name for spec in focused_tools(phase)),
        "operator_focus": operator_focus,
        "operator_annotation_images": annotation_images,
        "next_actions": next_actions,
        "can_promote": can,
        "acceptance": [_render(r) for r in results],
        "failing": [_render(r) for r in failing],
        "summary": summary,
    }


@needs("orchestrator")
def promote_phase(*, orchestrator: Any) -> dict[str, Any]:
    """Advance one phase, and only when the current phase's acceptance queries pass.

    A phase completes when its queries pass against live geometry, never when an agent says
    it is finished: agents self-report false success in 13-89% of failures, and a second
    agent reviewing that claim catches it at barely above chance.
    """
    before = orchestrator.phase
    can, results = _acceptance(orchestrator)
    failing = [r for r in results if not r.passed]

    if not can:
        raise ToolError(
            rule="orchestration.promotion_refused",
            detail=(
                f"phase {before.value!r} is not finished: "
                + "; ".join(_line(r) for r in failing)
            ),
            suggestion=(
                "fix each failing query above and call promote_phase again. There is no "
                "force parameter (ADR-012) — the queries are the only way through. "
                "get_phase() reports the same list at any time."
            ),
        )

    try:
        after = orchestrator.promote()
    except ValueError as exc:
        raise ToolError(
            rule="orchestration.promotion_refused",
            detail=str(exc),
            suggestion=(
                f"{before.value} is the last phase in the plan — there is nothing to "
                "promote to. Export from here (export_scene) rather than advancing."
            ),
        ) from exc

    return {
        "ok": True,
        "from": before.value,
        "to": after.value,
        "roles_legal_now": sorted(role.value for role in roles_for_phase(after)),
        "tools_callable_now": _tools_callable_in(after),
        "acceptance": [_render(r) for r in results],
        "summary": f"promoted {before.value} -> {after.value}; every acceptance query passed",
    }
