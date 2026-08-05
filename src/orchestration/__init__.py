"""``orchestration`` — the phase machine, the single write lock, conflict flagging, the
check-cadence policy, and assembly of the standard action report (ADR-007, ADR-005).

Phase gating *is* the concurrency-control mechanism, not a separate thing layered on top
of one (ADR-007) — many read-only INSPECT agents may run at once because none of their
tools can mutate, and exactly one write lease may be live at a time. This file is a
barrel: re-exports only, no logic. ``Orchestrator`` itself is assembled here from five
responsibility mixins, one per file, each covering a distinct decision (Rule 2):

| File | Owns |
|---|---|
| ``phases.py`` | phase machine, promotion, tool-role partitioning |
| ``locking.py`` | the single write lock (``contracts.WriteLockManager``) |
| ``proposals.py`` | propose / pending / conflict flagging / accept |
| ``reporting.py`` | perform, check cadence, action-report assembly |
| ``run.py`` | pause / resume / run state |
| ``scene_port.py`` | the typed slice of ``scene``'s future interface this module depends on |

Every method on every mixin raises ``NotImplementedError`` (Rule 4 — tests come first).
See ``CLAUDE.md`` for status and ``README.md`` for the full contract.
"""

from __future__ import annotations

from contracts import CheckCadence

from .locking import LockingMixin
from .phases import PhaseMixin
from .proposals import ProposalConflict, ProposalsMixin
from .reporting import ReportingMixin
from .run import RunMixin, RunPaused
from .scene_port import ScenePort

__all__ = ["Orchestrator", "ScenePort", "ProposalConflict", "RunPaused"]


class Orchestrator(PhaseMixin, LockingMixin, ProposalsMixin, ReportingMixin, RunMixin):
    """One orchestrator per running scene. See the module docstring above for what each
    of the five mixins owns, and ``README.md`` for the full public contract.

    Constructed with the ``scene`` module's public surface (``ScenePort``) and a starting
    check cadence. A real implementation will need more instance state than is stored
    here (pending proposals, the operator-note queue, the run state flag) — deliberately
    not added by this stub (Rule 4: no implementation before a failing test), so the
    fields below are exactly the two constructor arguments and nothing else.
    """

    def __init__(
        self, scene: ScenePort, *, cadence: CheckCadence = CheckCadence.EVERY_GEOMETRY_CHANGE
    ) -> None:
        self._scene = scene  # retained only so the stub's signature is exact
        self._cadence = cadence
