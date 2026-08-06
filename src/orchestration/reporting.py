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


def _touched(result: OperationResult) -> list[str]:
    """Objects an operation produced or modified, in order, without duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for obj in (*result.produced_objects, *result.modified_objects):
        if obj not in seen:
            seen.add(obj)
            out.append(obj)
    return out


class ReportingMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def _capture_snapshot(self, op: Operation) -> str:
        """Write the scene as it stands, and return the path.

        Called before an opaque operation runs, because that is the only moment the
        pre-execution state still exists. Without it `UndoBarrier.snapshot_path` pointed at
        nothing and undoing across a raw call re-executed the arbitrary script instead of
        restoring — a non-deterministic script then produced different geometry while the
        system reported a clean `FULL_RESYNC`.
        """
        import tempfile
        from pathlib import Path

        directory = Path(tempfile.gettempdir()) / "forge3d-snapshots"
        directory.mkdir(parents=True, exist_ok=True)
        path = str(directory / f"{op.op_id}.json")
        save = getattr(self._scene, "save", None)
        if save is None:
            # Better an honest marker than a path to a file that was never written: the
            # barrier still records that this point cannot be replayed across.
            return f"{path}#unavailable-no-save"
        save(path)
        return path

    def _measure(self, op: Operation, result: OperationResult) -> tuple[Measurement, ...]:
        """Real measurements against live geometry for what this operation touched.

        This is the product's core promise (Gate A 3.1, ADR-005): the tool computes the
        spatial facts so the model never eyeballs them. It emitted hardcoded zeroes for a
        while because `ScenePort` exposed no engine — B-000. The port now does, so this
        calls `measure` for real.

        Scoped to the changed objects (ADR-011): at thousands of objects a whole-scene
        sweep per call is not viable, and `MeasurementReport` records the scope so a clean
        result can never be mistaken for a whole-scene clean bill of health.

        Never raises. A measurement failure must not fail the operation that already
        succeeded — the report says less, the model still gets its result.
        """
        touched = _touched(result)
        if not touched:
            return ()
        engine = getattr(self._scene, "engine", None)
        if engine is None:
            return ()

        import measure

        out: list[Measurement] = []
        for obj in touched:
            try:
                out.append(measure.dimensions(engine, obj))
                out.append(measure.triangle_count(engine, obj))
            except Exception:  # noqa: BLE001 — a stale id must not sink the report
                continue
        return tuple(out)

    def _new_problems(self, result: OperationResult) -> tuple:
        """Defects that exist on the objects this operation just touched.

        Gate A 4.1 chose "what changed + key measurements + new problems". Without this the
        third of those three is always empty and the agent never learns that the railing it
        just placed now clips the tread — which is the whole reason the field exists.
        """
        touched = _touched(result)
        engine = getattr(self._scene, "engine", None)
        if engine is None or not touched:
            return ()

        import measure

        problems: list = []
        for obj in touched:
            try:
                problems.extend(measure.inspect(engine, obj))
            except Exception:  # noqa: BLE001
                continue
        return tuple(problems)

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

        # An opaque operation cannot be replayed, so rolling back across it needs a real
        # snapshot to restore from. Nothing in the wired product computed one, so raw
        # execution either raised outright or recorded a barrier that pointed at nothing —
        # while SECURITY.md claimed the barrier as a defence. Capturing it here, before the
        # code runs, is the only moment the pre-execution state still exists.
        snapshot_path = self._capture_snapshot(op) if op.opaque else ""

        # Forward the lease we just verified. Without it the real Scene sees no lock proof
        # and raises LockContention against the caller's own live lease, so every mutating
        # call through the agent path failed 100% of the time. Invisible in every suite
        # because both FakeScene doubles implement `apply(self, op)` with no lock check —
        # a double agreeing with the wrong side of the contract.
        result = self._scene.apply(op, lease=lease, snapshot_path=snapshot_path)

        if self._cadence is CheckCadence.EVERY_GEOMETRY_CHANGE:
            checks_skipped = False
        elif self._cadence is CheckCadence.PHASE_BOUNDARIES:
            checks_skipped = op.kind != "phase_promotion"
        else:  # CheckCadence.ON_REQUEST
            checks_skipped = True

        measurements = () if checks_skipped else self._measure(op, result)
        new_problems = () if checks_skipped else self._new_problems(result)

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
            new_problems=new_problems,
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
