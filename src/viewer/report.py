"""Turning an ``ActionReport`` — and the other three things only the layers *above*
``scene`` know about — into wire messages.

``translate.py`` can only ever see a ``contracts.SceneChangeEvent``, which says what
geometry moved and cannot say why, what it broke, or what it fixed. That content exists
one layer up, in ``orchestration``'s ``ActionReport``/``Conflict`` and ``export``'s
``ExportReport``. Without a path for it, ``LOG``, ``PROBLEMS``, ``CONFLICT`` and
``EXPORT_REPORT`` are four wire types ``frontend/src/main.js`` fully implements and the
backend never constructs.

The direction of the arrow is unchanged. Nothing here is a callback ``scene`` installs
*into* ``viewer``; these are public methods on ``ViewerBridge`` that a caller already
holding the bridge may call, and a caller that never calls them gets exactly the previous
behaviour. Every one of them swallows its own failures: ``Orchestrator.perform`` is the
single path every mutation takes, and a viewer that raises there would fail an operation
that had already succeeded — precisely the inversion the one-way dependency exists to
prevent.
"""

from __future__ import annotations

from contracts import (
    ActionReport,
    Conflict,
    Defect,
    ExportReport,
    RunState,
    ServerMessage,
    ServerMessageType,
)

__all__ = ["ReportMixin"]

MAX_DESCRIBED_PROBLEMS = 6
"""How many defects the one-line ``PROBLEMS`` text names before it stops.

The structured list in ``data`` is never truncated — this bound is about a log line
staying readable, not about what the client is told. A 39-defect line (a real number, from
a 4 m room) is one nobody reads.
"""


def _defect_payload(defect: Defect) -> dict:
    return {
        "defect_class": defect.defect_class.value,
        "severity": defect.severity.value,
        "object_id": defect.object_id,
        "detail": defect.detail,
        "magnitude": defect.magnitude,
    }


def _subjects(*groups: tuple[Defect, ...]) -> tuple[str, ...]:
    """Every object named by any of these defects, in order, without duplicates."""
    return tuple(dict.fromkeys(d.object_id for group in groups for d in group))


class ReportMixin:
    """Expects ``self._orchestrator``, ``self._next_seq()`` and ``self._enqueue()`` — see
    ``bridge.py``."""

    def report_action(self, report: ActionReport) -> None:
        """Publish one ``contracts.ActionReport`` to every watcher.

        This is the method ``orchestration``'s reporting layer calls after
        ``Orchestrator.perform`` builds a report — see ``README.md``'s "What still needs a
        caller". Never raises.
        """
        try:
            messages = self._action_messages(report)
        except Exception:  # noqa: BLE001 — a broken report must not fail the operation
            return
        for message in messages:
            self._enqueue(message)
        self._sweep_conflicts()

    def report_export(self, report: ExportReport) -> None:
        """Publish one ``EXPORT_REPORT`` — the export warning banner (Gate A 6.3).

        Kept off ``PROBLEMS`` for the reason ``ServerMessageType.EXPORT_REPORT``'s own
        docstring gives: an export banner is about a file that was written, not about the
        live scene. Never raises.
        """
        try:
            message = ServerMessage(
                type=ServerMessageType.EXPORT_REPORT,
                seq=self._next_seq(),
                text=report.banner,
                object_ids=_subjects(report.defects),
                data={
                    "path": report.path,
                    "profile": report.profile,
                    "ok": report.ok,
                    "triangle_count": report.triangle_count,
                    "budget": report.budget,
                    "over_budget_by": report.over_budget_by,
                    "forced": report.forced,
                    "defects": [_defect_payload(d) for d in report.defects],
                },
            )
        except Exception:  # noqa: BLE001
            return
        self._enqueue(message)

    def report_conflicts(self, *conflicts: Conflict) -> None:
        """Publish one ``CONFLICT`` per clash not already announced.

        Gate A 10.3: surfaced with the exact geometry involved, like a merge conflict, and
        never resolved silently. De-duplicated by ``conflict_id`` because
        ``Orchestrator.find_conflicts`` recomputes and returns the whole live set on every
        call — re-announcing an unresolved clash each time buries the new one. Never
        raises.
        """
        for conflict in conflicts:
            try:
                if conflict.conflict_id in self._seen_conflicts:
                    continue
                message = ServerMessage(
                    type=ServerMessageType.CONFLICT,
                    seq=self._next_seq(),
                    text=conflict.describe(),
                    object_ids=tuple(conflict.overlapping_objects),
                    data={
                        "conflict_id": conflict.conflict_id,
                        "detail": conflict.detail,
                        "authors": [p.author for p in conflict.proposals],
                        "proposal_ids": [p.proposal_id for p in conflict.proposals],
                        "magnitude": conflict.magnitude,
                        "unit": conflict.unit,
                        "location": conflict.location.as_tuple() if conflict.location else None,
                        "defects": [_defect_payload(d) for d in conflict.defects],
                    },
                )
            except Exception:  # noqa: BLE001
                continue
            self._seen_conflicts.add(conflict.conflict_id)
            self._enqueue(message)

    def report_run_state(self, state: RunState | None = None) -> None:
        """Publish ``RUN_STATE``, defaulting to whatever the attached orchestrator says.

        Carries the value in ``text`` *and* ``data["state"]``: ``frontend/src/main.js``
        renders ``run state → ${message.text}``, so a message with the value only in
        ``data`` displays "undefined". Never raises.
        """
        try:
            message = self._run_state_message(state)
        except Exception:  # noqa: BLE001
            return
        if message is not None:
            self._enqueue(message)

    # -- internals ---------------------------------------------------------------------

    def _run_state_message(
        self, state: RunState | None = None, *, seq: int | None = None
    ) -> ServerMessage | None:
        """``None`` when there is no orchestrator to ask — a viewer attached read-only has
        no run to report the state of, and inventing "running" would be a lie."""
        if state is None:
            if self._orchestrator is None:
                return None
            state = self._orchestrator.state
        value = getattr(state, "value", str(state))
        return ServerMessage(
            type=ServerMessageType.RUN_STATE,
            seq=self._next_seq() if seq is None else seq,
            text=value,
            data={"state": value},
        )

    def _action_messages(self, report: ActionReport) -> list[ServerMessage]:
        """Built in full before any of it is queued, so a half-translated report cannot
        leave the client holding a highlight with no log line explaining it."""
        messages: list[ServerMessage] = []
        changed = tuple(report.changed)
        if changed and changed != self._last_highlight:
            self._last_highlight = changed
            messages.append(
                ServerMessage(
                    type=ServerMessageType.HIGHLIGHT,
                    seq=self._next_seq(),
                    object_ids=changed,
                )
            )
        messages.append(self._log_message(report))
        problems = self._problems_message(report)
        if problems is not None:
            messages.append(problems)
        return messages

    def _log_message(self, report: ActionReport) -> ServerMessage:
        parts = [f"{report.op_id} — {report.summary}" if report.op_id else report.summary]
        if report.changed:
            parts.append(f"({len(report.changed)} object(s))")
        if report.removed:
            parts.append(f"(-{len(report.removed)} removed)")
        if not report.ok:
            parts.append(f"— {report.error_rule}: {report.error_detail}")
        if report.assumptions:
            parts.append("| assumed: " + "; ".join(report.assumptions))
        return ServerMessage(
            type=ServerMessageType.LOG,
            seq=self._next_seq(),
            text=" ".join(parts),
            data={
                "op_id": report.op_id,
                "ok": report.ok,
                "changed": list(report.changed),
                "removed": list(report.removed),
                "measurements": [m.describe() for m in report.measurements],
                "assumptions": list(report.assumptions),
                "checks_skipped": report.checks_skipped,
            },
        )

    def _problems_message(self, report: ActionReport) -> ServerMessage | None:
        """``None`` when there is genuinely nothing to say.

        A ``PROBLEMS`` message on every clean action is one log line per operation saying
        nothing, and a channel that mostly says nothing stops being read by the time it
        matters. ``checks_skipped`` is the exception and must always speak: silence on
        this channel reads as "checked, clean", which is the misreading
        ``ActionReport.checks_skipped``'s own docstring exists to forbid.
        """
        new = tuple(report.new_problems)
        resolved = tuple(report.resolved_problems)
        if not new and not resolved and not report.checks_skipped:
            return None

        if report.checks_skipped:
            text = "verification skipped by the cadence setting — not a clean result"
        else:
            counts: list[str] = []
            if new:
                counts.append(f"{len(new)} new")
            if resolved:
                counts.append(f"{len(resolved)} resolved")
            described = "; ".join(d.describe() for d in (*new, *resolved)[:MAX_DESCRIBED_PROBLEMS])
            text = f"{', '.join(counts)}: {described}"

        return ServerMessage(
            type=ServerMessageType.PROBLEMS,
            seq=self._next_seq(),
            text=text,
            object_ids=_subjects(new, resolved),
            data={
                "op_id": report.op_id,
                "new": [_defect_payload(d) for d in new],
                "resolved": [_defect_payload(d) for d in resolved],
                "checks_skipped": report.checks_skipped,
                "scope": report.checks_scope,
            },
        )

    def _sweep_conflicts(self) -> None:
        """Ask the attached orchestrator what clashes it currently knows about.

        ``Orchestrator.find_conflicts()`` is read-only and already computed on the
        proposal path. Sweeping it here is what makes ``CONFLICT`` reachable at all
        without ``orchestration`` having to learn that a viewer exists — which it must
        never do. An orchestrator that cannot answer (there is none, or it is an older
        one) is a legitimate configuration, not an error.
        """
        finder = getattr(self._orchestrator, "find_conflicts", None)
        if not callable(finder):
            return
        try:
            conflicts = tuple(finder())
        except Exception:  # noqa: BLE001
            return
        self.report_conflicts(*conflicts)
