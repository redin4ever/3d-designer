"""``orchestration`` — the phase machine, the single write lock, role authorisation, conflict
flagging, the check-cadence policy, and assembly of the standard action report
(ADR-007, ADR-005, ADR-012, ADR-013).

Phase gating *is* the concurrency-control mechanism, not a separate thing layered on top of
one (ADR-007) — many read-only INSPECT agents may run at once because none of their tools can
mutate, and exactly one write lease may be live at a time. This file is a barrel plus the
composition of ``Orchestrator`` from six responsibility mixins, one per file (Rule 2):

| File | Owns |
|---|---|
| ``phases.py`` | phase machine, the promotion gate, phase-filtered tool visibility |
| ``authorization.py`` | may this lease call this tool, in this phase (ADR-013) |
| ``locking.py`` | the single write lock (``contracts.WriteLockManager``) |
| ``proposals.py`` | propose / pending / conflict flagging / accept |
| ``reporting.py`` | perform, check cadence, action-report assembly |
| ``run.py`` | pause / resume / run state |

plus four private helpers those mixins share: ``_phase_acceptance.py`` (what "done" means per
phase), ``_suggested_fix.py`` (how a failure becomes a call an agent can make),
``_neighbours.py`` (which pairs the automatic check compares), and ``_summary.py`` (how much
of a report is worth sending). ``scene_port.py`` is now a one-line re-export: ``ScenePort``
moved into the frozen contract, where a double can no longer agree with the wrong side of it.

See ``CLAUDE.md`` for status and ``README.md`` for the full contract.
"""

from __future__ import annotations

import threading

from contracts import CheckCadence, Proposal, RunState, ScenePort, ToolRole, ToolSpec

from .authorization import AuthorizationMixin
from .locking import LockingMixin
from .phases import PhaseMixin, PromotionRefused
from .proposals import ProposalConflict, ProposalsMixin
from .reporting import ReportingMixin
from .run import RunMixin, RunPaused

__all__ = [
    "Orchestrator",
    "ScenePort",
    "ProposalConflict",
    "PromotionRefused",
    "RunPaused",
]


class Orchestrator(
    PhaseMixin,
    AuthorizationMixin,
    LockingMixin,
    ProposalsMixin,
    ReportingMixin,
    RunMixin,
):
    """One orchestrator per running scene. See the module docstring for what each mixin owns.

    Constructed with the ``scene`` module's public surface (``contracts.ScenePort``), a
    starting check cadence, and optionally the tool registry — injected rather than imported,
    because ``ARCHITECTURE.md``'s dependency arrow runs ``scene → orchestration → mcp`` and
    importing ``mcp_server`` here would reverse it. Instance state beyond those lives here,
    initialised once, so each mixin's methods have exactly one place to find it.

    **The three locks are not decoration.** Every method here can be reached from any thread:
    the writer performs, inspect agents read and propose concurrently *by design* (ADR-007),
    and a viewer socket calls ``pause``/``add_operator_note`` from its own. None of it was
    synchronised before this pass, and eight threads racing ``acquire`` produced *three*
    simultaneous winners in the first round of ``concurrency_test.py`` — each believing it
    held the only write lock. They are separate locks on purpose: a reader must never queue
    behind a writer's ``perform``, or "many read, one writes" becomes "one at a time" and the
    multi-agent design pays for coordination it does not get.
    """

    def __init__(
        self,
        scene: ScenePort,
        *,
        cadence: CheckCadence = CheckCadence.EVERY_GEOMETRY_CHANGE,
        registry: dict[ToolRole, tuple[ToolSpec, ...]] | None = None,
    ) -> None:
        self._scene = scene
        self._cadence = cadence
        self._registry = registry
        self._pending: list[Proposal] = []
        self._operator_notes: list[str] = []
        # Two operator channels with deliberately opposite lifetimes: annotations are events
        # and drain on delivery like notes; focus is standing state and does not (A-013).
        self._annotations: list = []
        self._focus: tuple[str, ...] = ()
        self._annotation_images: dict[str, str] = {}
        self._state: RunState = RunState.RUNNING
        self._lock_tick = 0
        self._index = None
        self._index_engine = None

        # Re-entrant: `accept` calls `perform`, and both are part of the write path.
        self._report_listeners: list = []
        self._write_mutex = threading.RLock()
        self._notes_mutex = threading.Lock()
        self._pending_mutex = threading.Lock()
