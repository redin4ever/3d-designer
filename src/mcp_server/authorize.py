"""Which tools a caller may reach right now — the role comes from the lease, and the
phase decides what any role may do (ADR-013, Gate B 6.3).

**This is not a security boundary, and nothing here contains anything.** ADR-009 gives
every connected agent arbitrary code execution and full disk access, by explicit user
choice: ``raw_execute`` runs whatever it is handed, with no sandbox, no allowlist and no
AST check, and adding one here would silently narrow a capability the user chose. What this
module is, is a *coordination and correctness* mechanism — it enforces the staged plan
(blockout, then refine, then detail, then polish) that Gate A 3.2 chose and that nothing
enforced until now.

The defect it closes, measured live against the real product: ``dispatch`` checked only
that a tool was visible to the role string **the caller supplied with its own call**, and
never compared that to the session's phase. ``unwrap_uvs`` (POLISH) and ``add_railing``
(REFINE) both succeeded in a session that had never left ``blockout``, and any agent could
hold any role by naming it.

Two authorities, deliberately separate:

- **The phase** says which roles may act at all (``contracts.roles_for_phase``). It applies
  to every call, with or without a lease.
- **The lease** says which of those roles *this* caller was granted
  (``contracts.WriteLease.granted_roles``). A caller cannot widen it: the lease is frozen,
  only the lock manager issues one, and the role a request declares is ignored outright.

A caller with no lease reaches ``INSPECT`` tools and nothing else (ADR-007: many readers,
one writer). Not every read-only tool — ``ADMIN`` is legal in every phase but its tools
mutate, and a read-only tool of some *other* role is still that role's business. That line
is drawn by ``orchestration.authorize``, which owns it.

**The decision is delegated, not duplicated.** ``Orchestrator.authorize(tool_name, roles,
lease)`` is the authority; this module calls it and re-raises its refusal as
:class:`PhaseRefusal`, which adds the one thing a refusal cannot work out from inside the
orchestrator — *which* phase would allow the tool. The local implementation below is a
fallback for an orchestrator that predates ADR-013 (a bare test double, an older
composition root); it deliberately mirrors the same two conditions, so the two cannot
disagree about who may do what.

Not part of ``mcp_server``'s public barrel — exercised through ``dispatch``.
"""

from __future__ import annotations

from typing import Any

from contracts import (
    PHASE_ORDER,
    PHASE_ROLES,
    Phase,
    PhaseViolation,
    RuleError,
    ToolRole,
    ToolSpec,
    WriteLease,
    roles_for_phase,
)

__all__ = ["authorize", "roles_held", "phases_allowing", "PhaseRefusal"]


def phases_allowing(roles: tuple[ToolRole, ...]) -> tuple[Phase, ...]:
    """Every phase in which one of ``roles`` may act — i.e. where this tool becomes legal."""
    return tuple(
        phase for phase in PHASE_ORDER if any(role in PHASE_ROLES.get(phase, ()) for role in roles)
    )


class PhaseRefusal(PhaseViolation):
    """:class:`contracts.PhaseViolation` plus the one thing it cannot work out for itself:
    *which* phase does allow this tool.

    ``PhaseViolation`` names the phase the session is in and the roles legal there. An agent
    refused an export in ``blockout`` still has to infer that POLISH is where EXPORT lives
    and that promotion is one step at a time. Since ADR-012 removed the promotion override,
    an inference it gets wrong has no escape hatch behind it — so the refusal states it.
    """

    def __init__(
        self,
        tool: str,
        held: tuple[ToolRole, ...],
        phase: Phase,
        *,
        required: tuple[ToolRole, ...] = (),
    ) -> None:
        super().__init__(tool, held, phase, required=required)
        allowed_in = phases_allowing(required)
        if allowed_in and phase not in allowed_in:
            self.suggestion += (
                f" {tool!r} becomes legal in phase(s) "
                f"{', '.join(p.value for p in allowed_in)}; the session is in "
                f"{phase.value!r} and promote_phase advances exactly one step at a time, "
                "only when the current phase's acceptance queries pass (call get_phase to "
                "see which ones fail)."
            )
        RuleError.__init__(self, self.rule, self.detail, self.suggestion)


LEASELESS_ROLES: tuple[ToolRole, ...] = (ToolRole.INSPECT,)
"""What a caller holding no write lease may reach — mirrors
``orchestration.authorization._LEASELESS_ROLES``. ``INSPECT`` alone, not all of
``ALWAYS_LEGAL_ROLES``: ``ADMIN`` is legal in every phase, but its tools (checkpoint,
rollback, raw execution) mutate, and a lease-less caller reaching a mutating tool is the
write lock being advisory for exactly the callers least likely to have taken it."""


def roles_held(lease: WriteLease | None, phase: Phase) -> tuple[ToolRole, ...]:
    """The roles this caller actually holds in ``phase``.

    With no lease, ``INSPECT`` and nothing else. With a lease, its grant narrowed to the
    phase — ``WriteLease.granted_roles`` narrows against the lease's *own* recorded phase,
    which goes stale the moment the session promotes, so the narrowing is redone against the
    session's phase here. A lease held across a promotion must follow the session, or the
    phase gate would be escapable by simply holding on.
    """
    legal = roles_for_phase(phase)
    if lease is None:
        return tuple(role for role in LEASELESS_ROLES if role in legal)
    if not lease.roles:
        return legal
    return tuple(role for role in lease.roles if role in legal)


def _authorize_locally(
    spec: ToolSpec, phase: Phase, lease: WriteLease | None
) -> tuple[ToolRole, ...]:
    held = roles_held(lease, phase)
    if not any(role in held for role in spec.roles):
        raise PhaseRefusal(spec.name, held, phase, required=spec.roles)
    return tuple(role for role in spec.roles if role in held)


def authorize(
    spec: ToolSpec, *, orchestrator: Any, lease: WriteLease | None
) -> tuple[ToolRole, ...]:
    """Raise :class:`PhaseRefusal` unless ``spec`` may be called right now; otherwise return
    the roles under which it was permitted.

    The role the caller declared is not a parameter here, and that is the whole point.

    ``Orchestrator.authorize`` decides. Its refusal is re-raised as :class:`PhaseRefusal` so
    that the message gains the phase in which the tool *would* be legal — an addition, never
    a second opinion: the fields come straight off the exception it raised. When the
    orchestrator has no ``authorize`` (a bare double, or a composition root from before
    ADR-013), the same two conditions are applied here instead, so a missing method can
    never mean a missing check.
    """
    phase: Phase = orchestrator.phase
    delegate = getattr(orchestrator, "authorize", None)
    if not callable(delegate):
        return _authorize_locally(spec, phase, lease)

    try:
        delegate(spec.name, tuple(spec.roles), lease)
    except PhaseViolation as exc:
        raise PhaseRefusal(
            spec.name, getattr(exc, "held", ()), getattr(exc, "phase", phase),
            required=getattr(exc, "required", tuple(spec.roles)),
        ) from exc
    return tuple(role for role in spec.roles if role in roles_held(lease, phase))
