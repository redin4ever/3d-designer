"""The action loop: apply one operation, check it, and hand back one report (Gate A 4.1).

``perform`` is the single path every mutation takes — direct agent calls and
``proposals.accept`` alike are expected to route through it (or through the same
machinery), so cadence, operator notes and lock verification are decided in exactly one
place. ADR-005: geometry checks run after every geometry-changing operation at a
user-configurable cadence, and report rather than block by default. Gate A 4.1: the
report is "what changed + key measurements + new problems", never full scene state and
never a bare pass/fail.

Nothing here computes anything yet — every method raises until an implementer replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import ActionReport, CheckCadence, Operation, WriteLease

_NOT_IMPLEMENTED = "orchestration.{name}: not implemented"


class ReportingMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def perform(self, op: Operation, lease: WriteLease) -> ActionReport:
        """Apply ``op`` and return the standard report.

        Once implemented, in this order:

        1. ``self.verify(lease)`` — raise :class:`contracts.LockContention` and change
           nothing if ``lease`` is not the live one. A caller that cannot present a live
           lease must never reach ``self._scene.apply``; the lock is what makes that
           true.
        2. Check ``self.state``: if :attr:`contracts.RunState.PAUSED`, raise
           ``orchestration.RunPaused`` (see ``run.py``) without touching ``self._scene``
           at all. This module's chosen answer to "raise or defer": raise, and check
           *before* ``self._scene.apply`` runs — pause is cooperative, checked between
           operations and never mid-operation, so the log is never left half-applied
           (``contracts.RunState.PAUSED``'s own docstring).
        3. ``self._scene.apply(op)``.
        4. Decide, from the current cadence (``self._cadence``), whether to run
           measurement now: ``EVERY_GEOMETRY_CHANGE`` always does; ``PHASE_BOUNDARIES``
           only at a phase promotion; ``ON_REQUEST`` only when asked explicitly (a
           separate call, not modelled by ``perform`` itself). When skipped,
           ``ActionReport.checks_skipped`` must be ``True`` — its own ``render()``
           already refuses to let that read as a clean result; this method's only job is
           to set the flag honestly.
        5. Drain ``self._operator_notes`` into the report's ``operator_notes`` and clear
           the internal list — MCP is call/response, so a redirect typed mid-run has
           exactly one path out (``ActionReport.operator_notes``'s own docstring), and it
           must be delivered exactly once, never replayed on a later, unrelated call.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="perform"))

    def set_cadence(self, c: CheckCadence) -> None:
        """Change the check cadence, effective on the very next ``perform`` call — a
        settings-menu control (Gate A 3.1: "with a settings menu setting that enables me
        changing that"), not a value read once at construction and then frozen."""
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="set_cadence"))

    def add_operator_note(self, text: str) -> None:
        """Queue free text typed mid-run for delivery on the next ``ActionReport`` (see
        ``perform``, step 5). Queued rather than sent immediately because MCP is
        call/response — there is no channel into a connected agent's context except the
        next tool response."""
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_operator_note"))
