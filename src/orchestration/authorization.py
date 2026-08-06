"""May this lease call this tool, in this phase? (ADR-013)

Its own file because it is its own decision, and a small, sharp one: two set intersections
and a refusal message that has to be good enough for an agent with no human to ask. It sits
between ``locking.py`` (which issues the authority) and ``phases.py`` (which owns what the
phase permits) and borrows the table from neither — ``WriteLease.permits`` and
``contracts.roles_for_phase`` are the two things it calls, and it re-derives nothing.

What this refuses is the ordering Phase 6 found broken against the running product:
``unwrap_uvs`` (POLISH) and ``add_railing`` (REFINE) both succeeded while the session had
never left ``blockout``, because ``dispatch`` compared the requested tool against the role
string *the caller itself supplied* and never compared either to the session's phase.
"""

from __future__ import annotations

from contracts import PhaseViolation, ToolRole, WriteLease, roles_for_phase

__all__ = ["AuthorizationMixin"]

_LEASELESS_ROLES: tuple[ToolRole, ...] = (ToolRole.INSPECT,)
"""What a caller with no write lease may reach.

``INSPECT`` alone, deliberately — not all of ``ALWAYS_LEGAL_ROLES``. ``ADMIN`` is always
legal in every *phase*, but its tools (checkpoint, rollback, raw execution) mutate, and a
lease-less caller reaching a mutating tool is the write lock being advisory for exactly the
callers most likely not to have acquired one.
"""


class AuthorizationMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def authorize(
        self, tool_name: str, roles: tuple[ToolRole, ...], lease: WriteLease | None = None
    ) -> None:
        """Raise :class:`contracts.PhaseViolation` unless this call is permitted right now.

        ``roles`` is the tool's **declared** roles — ``ToolSpec.roles``, read from the
        registry — not a role the caller claims for itself. That distinction is the whole of
        ADR-013: authority comes from ``lease``, the request's own claim is ignored, and
        passing ``ToolRole.POLISH`` here grants nothing.

        Two independent conditions, both required:

        1. At least one of ``roles`` is legal in ``self.phase``
           (:func:`contracts.roles_for_phase`). Checked against the *session's* phase, not
           the lease's — a lease issued in ``blockout`` and still held after a promotion must
           follow the session, or the phase gate would be escapable by holding on.
        2. The lease permits at least one of ``roles`` (:meth:`contracts.WriteLease.permits`).
           With no lease, only :data:`_LEASELESS_ROLES` passes, which is what lets any number
           of INSPECT agents run beside the one writer (ADR-007).

        Returns ``None`` on success. It is a guard, not a query: a method that returned a
        boolean would be one forgotten ``if`` away from enforcing nothing, and this is the
        check the phase split rests on.
        """
        legal_here = roles_for_phase(self.phase)
        if not any(role in legal_here for role in roles):
            raise PhaseViolation(
                tool=tool_name,
                held=lease.granted_roles() if lease is not None else (),
                phase=self.phase,
                required=tuple(roles),
            )

        if lease is None:
            if any(role in _LEASELESS_ROLES for role in roles):
                return
            raise PhaseViolation(
                tool=tool_name, held=(), phase=self.phase, required=tuple(roles)
            )

        if not lease.permits(tuple(roles)):
            raise PhaseViolation(
                tool=tool_name,
                held=lease.granted_roles(),
                phase=self.phase,
                required=tuple(roles),
            )
