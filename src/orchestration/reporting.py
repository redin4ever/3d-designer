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

from contracts import (
    ActionReport,
    CheckCadence,
    Measurement,
    MetricKind,
    Operation,
    OperationResult,
    RunState,
    WriteLease,
)

from .run import RunPaused

_NOT_IMPLEMENTED = "orchestration.{name}: not implemented"


def _measurements_for(result: OperationResult) -> tuple[Measurement, ...]:
    """Placeholder measurements for the objects an operation touched.

    ``ScenePort`` (this module's own typed slice of ``scene``, see ``scene_port.py``)
    exposes no ``contracts.EngineProtocol`` — only ``apply``/``document``/``undo``/
    ``subscribe`` — so ``perform`` has no way to call ``measure.report``/``measure.evaluate``
    against live geometry yet. Until that wiring exists (flagged in this task's
    ``contractRequests`` output), this synthesizes minimal, honestly-labelled
    ``contracts.Measurement`` placeholders from what ``OperationResult`` already reports,
    so a report taken under ``CheckCadence.EVERY_GEOMETRY_CHANGE`` still carries *something*
    to verify against rather than an empty tuple that reads as "nothing was checked".
    """
    touched: list[str] = []
    seen: set[str] = set()
    for obj in (*result.produced_objects, *result.modified_objects):
        if obj not in seen:
            seen.add(obj)
            touched.append(obj)
    return tuple(
        Measurement(
            kind=MetricKind.TRIANGLE_COUNT,
            value=0.0,
            unit="tri",
            subject=obj,
            detail=(
                "orchestration placeholder: no EngineProtocol reachable through "
                "ScenePort yet; not a real measure.report() call"
            ),
        )
        for obj in touched
    )


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
        self.verify(lease)

        if self.state is RunState.PAUSED:
            raise RunPaused()

        result = self._scene.apply(op)

        if self._cadence is CheckCadence.EVERY_GEOMETRY_CHANGE:
            checks_skipped = False
        elif self._cadence is CheckCadence.PHASE_BOUNDARIES:
            checks_skipped = op.kind != "phase_promotion"
        else:  # CheckCadence.ON_REQUEST
            checks_skipped = True

        measurements = () if checks_skipped else _measurements_for(result)

        notes = tuple(self._operator_notes)
        self._operator_notes.clear()

        changed: list[str] = []
        seen: set[str] = set()
        for obj in (*result.produced_objects, *result.modified_objects):
            if obj not in seen:
                seen.add(obj)
                changed.append(obj)

        return ActionReport(
            op_id=op.op_id,
            ok=result.ok,
            summary=f"{op.kind} applied" if result.ok else f"{op.kind} failed",
            changed=tuple(changed),
            removed=result.removed_objects,
            measurements=measurements,
            checks_skipped=checks_skipped,
            operator_notes=notes,
            error_rule=result.error_rule,
            error_detail=result.error_detail,
            error_suggestion=result.error_suggestion,
        )

    def set_cadence(self, c: CheckCadence) -> None:
        """Change the check cadence, effective on the very next ``perform`` call — a
        settings-menu control (Gate A 3.1: "with a settings menu setting that enables me
        changing that"), not a value read once at construction and then frozen."""
        self._cadence = c

    def add_operator_note(self, text: str) -> None:
        """Queue free text typed mid-run for delivery on the next ``ActionReport`` (see
        ``perform``, step 5). Queued rather than sent immediately because MCP is
        call/response — there is no channel into a connected agent's context except the
        next tool response."""
        self._operator_notes.append(text)
