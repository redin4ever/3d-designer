"""The action loop: apply one operation, check it, and hand back one report (Gate A 4.1).

``perform`` is the single path every mutation takes — direct agent calls and
``proposals.accept`` alike route through it — so cadence, operator notes, lock verification
and report size are decided in exactly one place. ADR-005: geometry checks run after every
geometry-changing operation at a user-configurable cadence, and report rather than block.
Gate A 4.1: the report is "what changed + key measurements + new problems", never full scene
state and never a bare pass/fail.

Two things live in sibling files because they are separate decisions (Rule 2):
``_neighbours.py`` owns *which pairs* the check compares, and ``_summary.py`` owns *how much*
of the result is worth sending.
"""

from __future__ import annotations

import logging
from typing import Iterable

from contracts import (
    ActionReport,
    CheckCadence,
    Defect,
    Operation,
    OperationResult,
    OperatorAnnotation,
    RunState,
    WriteLease,
)

from ._neighbours import NeighbourIndex
from ._phase_acceptance import VISUAL_GAP_MAX
from ._summary import Detail, summarise
from .run import RunPaused

log = logging.getLogger(__name__)


def _touched(result: OperationResult) -> tuple[str, ...]:
    """Objects an operation produced or modified, in order, without duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for obj in (*result.produced_objects, *result.modified_objects):
        if obj not in seen:
            seen.add(obj)
            out.append(obj)
    return tuple(out)


class ReportingMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def _capture_snapshot(self, op: Operation) -> str:
        """The restorable pre-execution state for an opaque operation.

        Delegates to ``ScenePort.capture_snapshot``, which writes the live **geometry**. This
        module used to implement it by calling ``scene.save()``, which serialises the
        operation *log* — and an opaque operation is by definition one whose effect the log
        does not describe. Restoring from it restored nothing: undo across a raw-execution
        barrier re-ran the script, so a non-deterministic script produced one object, then
        three differently-named ones after undo-then-redo, while the system reported a clean
        ``FULL_RESYNC`` (Gate B 5.3).

        A scene that cannot capture one gets an honest marker rather than a path to a file
        nobody wrote. The barrier still records that this point cannot be replayed across,
        which is the half of the guarantee that survives.
        """
        capture = getattr(self._scene, "capture_snapshot", None)
        if capture is not None:
            try:
                path = capture(op.op_id)
            except Exception:  # noqa: BLE001 — an honest marker beats a bogus path
                path = ""
            if path:
                return path
        return f"{op.op_id}#unavailable-no-capture-snapshot"

    def _engine(self):
        return getattr(self._scene, "engine", None)

    def _neighbour_index(self, engine) -> NeighbourIndex:
        """One index per engine, kept alive across operations (ADR-011).

        Rebuilt only if the engine underneath changes, which in practice never happens — but
        an index silently answering for a different engine is a wrong answer that looks
        exactly like a right one.
        """
        if getattr(self, "_index_engine", None) is not engine:
            self._index_engine = engine
            self._index = NeighbourIndex(engine)
        return self._index

    def _detail(self, changed: tuple[str, ...]) -> Detail:
        """Measurements for what changed, summarised if there is too much of it."""
        engine = self._engine()
        if engine is None or not changed:
            return Detail()
        return summarise(engine, changed)

    def _new_problems(self, op: Operation, result: OperationResult) -> tuple[Defect, ...]:
        """Defects on what this operation touched **and between it and its neighbours**.

        The single-object checks (``measure.inspect``) cannot see a part interpenetrating a
        *different* part — that is a pairwise question, and ``inspect``'s own docstring says
        it excludes them. Running only those while stamping every report
        ``checks_scope="changed+neighbours"`` is how a 4 m room produced 39 real clipping
        defects and reported none.

        ``op.joinery`` is passed through because no library can tell a post socketed into a
        deck from two posts overlapping — both are identical BVH overlaps, and the difference
        is declared intent, never inferred. Without it every intentional joint in a model
        comes back as a defect and the agent learns to ignore the channel.

        Never raises. A check that fails must not fail the operation that already succeeded.
        """
        import measure

        touched = _touched(result)
        engine = self._engine()
        if engine is None or not touched:
            return ()

        problems: list[Defect] = []
        for object_id in touched:
            try:
                problems.extend(measure.inspect(engine, object_id))
            except Exception:  # noqa: BLE001
                continue

        try:
            pairs = self._neighbour_index(engine).pairs_touching(touched, VISUAL_GAP_MAX)
        except Exception:  # noqa: BLE001
            return tuple(problems)

        if pairs:
            try:
                problems.extend(measure.find_clipping(engine, pairs, op.joinery))
            except Exception:  # noqa: BLE001
                pass
            try:
                problems.extend(measure.find_visual_gaps(engine, pairs, VISUAL_GAP_MAX))
            except Exception:  # noqa: BLE001
                pass
        return tuple(problems)

    def _checks_skipped(self, op: Operation) -> bool:
        if self._cadence is CheckCadence.EVERY_GEOMETRY_CHANGE:
            return False
        if self._cadence is CheckCadence.PHASE_BOUNDARIES:
            return op.kind != "phase_promotion"
        return True  # CheckCadence.ON_REQUEST

    def perform(self, op: Operation, lease: WriteLease) -> ActionReport:
        """Apply ``op`` and return the standard report.

        In this order, and the order is the contract:

        1. ``self.verify(lease)`` — nothing reaches ``self._scene.apply`` without the live
           write lease. The lock is what makes that true.
        2. Refuse if the run is paused, *before* applying. Pause is cooperative — checked
           between operations, never mid-operation — so a paused run never has a half-applied
           operation to resume into.
        3. Capture a snapshot if ``op`` is opaque; that is the only moment the pre-execution
           state still exists.
        4. Apply, then check at the configured cadence, honestly marking ``checks_skipped``.
        5. Drain the operator-note queue exactly once.

        The whole write path holds ``self._write_mutex``. ``SceneDocument.append`` truncates
        anything past ``head``, and two threads inside it at once can have one truncate the
        other's just-appended operation away while its ``perform`` still reports success —
        a lost operation nobody is told about, in a log that is the source of truth for the
        geometry.
        """
        self.verify(lease)
        if self.state is RunState.PAUSED:
            raise RunPaused()

        with self._write_mutex:
            self.verify(lease)  # re-checked under the mutex: step 1 was outside it
            snapshot_path = self._capture_snapshot(op) if op.opaque else ""
            result = self._scene.apply(op, lease=lease, snapshot_path=snapshot_path)

            checks_skipped = self._checks_skipped(op)
            changed = _touched(result)
            detail = Detail() if checks_skipped else self._detail(changed)
            new_problems = () if checks_skipped else self._new_problems(op, result)

        with self._notes_mutex:
            notes = tuple(self._operator_notes)
            self._operator_notes.clear()
            annotations = tuple(self._annotations)
            self._annotations.clear()
            # Read, never cleared. This is the one piece of operator state that outlives its
            # own delivery, and it is the whole of Q-10: an instruction the agent re-reads
            # every turn rather than one it is told once and then forgets.
            focus = self._focus

        report = ActionReport(
            op_id=op.op_id,
            ok=result.ok,
            summary=f"{op.kind} applied" if result.ok else f"{op.kind} failed",
            changed=changed,
            removed=result.removed_objects,
            measurements=detail.measurements,
            new_problems=new_problems,
            checks_skipped=checks_skipped,
            operator_notes=notes,
            operator_annotations=annotations,
            operator_focus=focus,
            assumptions=result.assumptions,
            breakdown=detail.breakdown,
            detail_omitted=detail.detail_omitted,
            detail_hint=detail.detail_hint,
            total_triangles=detail.total_triangles,
            error_rule=result.error_rule,
            error_detail=result.error_detail,
            error_suggestion=result.error_suggestion,
        )
        self._publish(report)
        return report

    def on_report(self, listener) -> None:
        """Register something to be told about every :class:`ActionReport` this run produces.

        The one arrow from the write path out to anything watching it. ``viewer`` already
        knew how to turn a report into ``HIGHLIGHT``/``LOG``/``PROBLEMS`` messages —
        ``ViewerBridge.report_action`` — and nothing ever called it, so a person with the
        live view open saw meshes appear and was told nothing about what the agent had just
        done or found.

        A listener, rather than importing ``viewer`` here: the dependency arrow points from
        the web layer into the core and never back (``ARCHITECTURE.md``), so the composition
        root does the wiring and this side stays ignorant of who is listening.
        """
        self._report_listeners.append(listener)

    def _publish(self, report: ActionReport) -> None:
        """Tell every listener, and never let one of them break the operation.

        Each in its own try, not one around the loop: a single raising listener must not
        stop the ones after it from being told — the same rule ``scene._emit`` follows, and
        for the same reason. A broken viewer must not be able to fail a geometry write.
        """
        for listener in self._report_listeners:
            try:
                listener(report)
            except Exception:  # noqa: BLE001
                log.exception("orchestration: a report listener raised; continuing")

    def set_cadence(self, c: CheckCadence) -> None:
        """Change the check cadence, effective on the very next ``perform`` call — a
        settings-menu control (Gate A 3.1: "with a settings menu setting that enables me
        changing that"), not a value read once at construction and then frozen."""
        self._cadence = c

    @property
    def focus(self) -> tuple[str, ...]:
        """The parts the operator has marked as important.

        Readable outside the write path on purpose: an idle run performs nothing, and the
        operator can mark parts while it is idle. The MCP tool that hands an agent its
        operator context is exactly that caller.
        """
        with self._notes_mutex:
            return self._focus

    def set_focus(self, object_ids: Iterable[str]) -> None:
        """Replace the focus set — the whole set, never a delta (Q-11).

        Replacing rather than accumulating is what keeps the backend and the operator's own
        screen in agreement. The browser sends everything currently marked each time; if this
        merged instead, unmarking something in the UI would leave it marked here, forever, and
        the screen showing the truth would be the wrong one.

        Held under ``_notes_mutex`` with the other operator state: a viewer socket calls this
        from its own thread while the agent's thread is inside ``perform``.
        """
        with self._notes_mutex:
            self._focus = tuple(object_ids)

    def add_annotation(self, annotation: OperatorAnnotation) -> None:
        """Queue one annotation for delivery on the next :class:`ActionReport`.

        Queued and then drained, exactly like an operator note and for the same reason — MCP
        is call/response, so the next tool response is the only channel into a connected
        agent's context. Unlike focus, this is an event: it is delivered once.
        """
        with self._notes_mutex:
            self._annotations.append(annotation)

    def add_operator_note(self, text: str) -> None:
        """Queue free text typed mid-run for delivery on the next ``ActionReport``. Queued
        rather than sent immediately because MCP is call/response — there is no channel into
        a connected agent's context except the next tool response."""
        with self._notes_mutex:
            self._operator_notes.append(text)
