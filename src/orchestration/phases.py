"""The phase machine and tool-role partitioning (ADR-007, ADR-003, ADR-005).

Phase gating *is* the concurrency-control mechanism (see ``locking.py``'s module
docstring) — not a separate thing that cooperates with one. A phase only hands off when
its acceptance queries pass against live geometry (ADR-005), never when an agent claims
it is finished; ``force=True`` is the one override, and it must be recorded rather than
silent (Gate A 6.3).

Nothing here computes anything yet — every method raises until an implementer replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import AcceptanceResult, Phase, ToolRole, ToolSpec

_NOT_IMPLEMENTED = "orchestration.{name}: not implemented"


class PhaseMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    @property
    def phase(self) -> Phase:
        """The current phase. Once implemented, reads
        ``self._scene.document().phase`` — ``contracts.SceneDocument`` already carries
        this field, so orchestration is not a second source of truth for it."""
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="phase"))

    def can_promote(self) -> tuple[bool, tuple[AcceptanceResult, ...]]:
        """Whether the current phase's acceptance queries all pass right now, and the
        full list of results — not just the failures — so a caller can show what passed
        too. The boolean and the results must agree: ``False`` with every
        ``AcceptanceResult.passed`` ``True`` would itself be a bug in whatever computes
        this."""
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="can_promote"))

    def promote(self, *, force: bool = False) -> Phase:
        """Advance to the phase immediately after the current one in
        :data:`contracts.PHASE_ORDER`.

        Once implemented:

        - Raises :class:`ValueError` if the current phase is already
          :attr:`contracts.Phase.POLISH` — there is no phase after it, and ``force``
          does not change that; forcing overrides a failing *check*, not the existence
          of a next phase.
        - With ``force=False``, raises :class:`ValueError` unless
          ``self.can_promote()[0]`` is ``True`` — a phase hands off when its acceptance
          queries pass against live geometry (ADR-005), never on request alone.
        - With ``force=True``, promotes regardless of ``can_promote()``, and *records*
          the override rather than promoting silently (Gate A 6.3: the user chose
          report-over-block, and that choice is only honoured if it stays visible
          afterward). This module's working convention: route the transition through
          ``self._scene.apply(Operation(kind="phase_promotion", phase=new_phase.value,
          author="orchestrator", params={"from": old_phase.value, "to":
          new_phase.value, "forced": force, "failing": tuple(r.query_id for r in
          results if not r.passed)}))`` and set ``self._scene.document().phase =
          new_phase`` — reusing the log ``scene`` already keeps, and its existing
          subscriber notification (``ScenePort.subscribe``), rather than inventing a
          second audit channel. This is this module's own assumption, not yet frozen
          anywhere in ``src/contracts/`` (see this task's ``contractRequests`` output).
        - Only ever moves one step — there is no parameter to name a target phase, so
          "skip a phase" is structurally unreachable, not merely refused.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="promote"))

    def tools_for(self, role: ToolRole) -> tuple[ToolSpec, ...]:
        """The tools visible to ``role`` right now.

        Contract, not yet sourced: between 1 and 8 tools always. The accuracy-optimal
        visible-set size measures roughly 2-7, with real degradation reported past
        ~10-15 (``contracts.ToolRole``'s own docstring); the upper bound here is
        load-bearing, not a style preference. :attr:`contracts.ToolRole.INSPECT` must
        receive only ``ToolSpec(mutating=False)`` entries — ``ToolSpec.__post_init__``
        already refuses to *construct* the opposite combination, so a registry built
        correctly cannot violate this, but ``tools_for`` must still not mis-filter and
        hand an inspect agent a mutating tool that belongs to a different role's slice
        of a shared registry.

        Where the registry itself comes from is an open implementation decision — a
        static table this module owns, or one composed by ``mcp`` and injected some
        other way than the constructor shown in this module's brief — flagged in this
        task's ``contractRequests`` output rather than decided here.
        """
        raise NotImplementedError(_NOT_IMPLEMENTED.format(name="tools_for"))
