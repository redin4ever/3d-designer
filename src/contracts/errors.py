"""The one error shape, and the exceptions that share it.

Gate A 4.2, verbatim: the agent is told *"what rule it broke"*. Phase 6 found that promise
half-kept — validation failures named a rule, and failures deeper in the geometry code
reached the agent as raw Python tracebacks, because the boundary caught exactly one
exception type and every module had defined its own error shape independently.

:class:`RuleError` is the shared base that makes "does this failure name a rule" a single
``isinstance`` check rather than four duck-typed ones. ``EngineError``, ``ToolError``,
``LockContention``, ``RunPaused`` and ``ProposalConflict`` all derive from it, so the
boundary can catch one type, and anything that does *not* derive from it is by definition
an unnamed failure that needs wrapping (ADR-013's refusal messages depend on this, and so
does the broad catch in ``app/handlers.py``).

Sits **first** in this package's import order — below ``geometry`` — because every other
module here may need to raise. That is the only ordering change since the package froze:
``errors → geometry → engine → measurement → constraints → export_profiles → operations →
phases → scene_doc → wire``.
"""

from __future__ import annotations

__all__ = ["RuleError", "RunPaused", "ProposalConflict"]


class RuleError(RuntimeError):
    """A failure that names the rule it broke, what happened, and what to try next.

    ``RuntimeError`` rather than ``Exception`` so that ``EngineError`` and
    ``LockContention`` keep the base they already had — no existing ``except`` clause
    anywhere changes meaning by this class being introduced beneath them.

    The three fields are not optional decoration. An agent handed an opaque error retries
    the same failing call, forever; practitioner reports are consistent on this. A
    ``suggestion`` that says nothing actionable is the same failure wearing a different
    hat, so subclasses that cannot offer one should say *why* rather than pass ``""``.
    """

    def __init__(self, rule: str, detail: str, suggestion: str = "") -> None:
        super().__init__(f"{rule}: {detail}" + (f" — {suggestion}" if suggestion else ""))
        self.rule = rule
        self.detail = detail
        self.suggestion = suggestion

    def as_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "detail": self.detail, "suggestion": self.suggestion}


class RunPaused(RuleError):
    """A mutating call arrived while the run is paused.

    Cooperative pause (ADR-006): checked *between* operations, never mid-operation, so the
    log is never truncated to a half-applied state. Lives here rather than in
    ``orchestration`` because ``mcp_server`` and ``viewer`` both need to name it — which
    is the contract request that had been open since Phase 4.
    """

    def __init__(self, detail: str = "the run is paused", suggestion: str = "resume the run, or send a redirect note") -> None:
        super().__init__(rule="orchestration.run_paused", detail=detail, suggestion=suggestion)


class ProposalConflict(RuleError):
    """Two or more proposals that cannot both be applied.

    Never resolved silently (Gate A 10.3). For geometry, last-writer-wins produces an
    invalid model rather than a surprise — one agent moving a wall while another attaches
    a railing to it. The conflicting proposal ids travel with the error so a caller can
    render the clash without re-deriving it.
    """

    def __init__(self, proposal_ids: tuple[str, ...], detail: str, suggestion: str = "") -> None:
        super().__init__(
            rule="orchestration.proposal_conflict",
            detail=detail,
            suggestion=suggestion or "resolve the overlap explicitly; nothing is applied until you do",
        )
        self.proposal_ids = proposal_ids
