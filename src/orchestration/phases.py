"""The phase machine, the promotion gate, and tool-role partitioning (ADR-012, ADR-013).

Phase gating *is* the concurrency-control mechanism (see ``locking.py``'s module docstring)
— not a separate thing that cooperates with one. A phase hands off when its acceptance
queries pass against live geometry (ADR-005), never when an agent claims it is finished.

**There is no override.** ``promote(force=True)`` is gone, deleted at Gate B 1.1 by ADR-012
along with ``PhasePromotion.allow_override`` in the frozen contract. What shipped in pass 1
was neither a gate nor an override: it promoted whenever the phase had recorded any operation
at all, and ``measure.evaluate`` had zero non-test call sites anywhere in the product.

What "done" means per phase lives in ``_phase_acceptance.py``; how a failure becomes a call
an agent can make lives in ``_suggested_fix.py``. Both are separate decisions from the state
machine here, and both are now load-bearing rather than informational — with no override, a
refusal is all an unattended agent has to work from.
"""

from __future__ import annotations

import uuid

from contracts import (
    PHASE_ORDER,
    AcceptanceResult,
    Operation,
    Phase,
    RuleError,
    ToolRole,
    ToolSpec,
    roles_for_phase,
)

from ._neighbours import NeighbourIndex
from ._phase_acceptance import VISUAL_GAP_MAX, evaluate_phase


class PromotionRefused(RuleError, ValueError):
    """The current phase's acceptance queries do not pass, so it cannot hand off (ADR-012).

    Two bases on purpose. :class:`contracts.RuleError` is what makes "does this failure name
    a rule" one ``isinstance`` check at the MCP boundary, and carries the ``suggestion`` an
    agent needs now that ADR-012 has left it no override to escape with. ``ValueError`` keeps
    the shape ``promote`` already raised for "there is no phase after polish", so a caller
    that catches one catches both — this module does not get to make callers learn a second
    exception for the same verb.
    """

    def __init__(self, phase: Phase, failures: tuple[AcceptanceResult, ...]) -> None:
        lines = "; ".join(f.describe() for f in failures)
        super().__init__(
            rule="orchestration.promotion_refused",
            detail=(
                f"phase {phase.value!r} has {len(failures)} failing acceptance "
                f"query(ies): {lines}"
            ),
            suggestion=(
                "there is no override (ADR-012). Run the suggested operation on each failing "
                "query above — every one of them names a call — then promote again."
            ),
        )
        self.phase = phase
        self.failures = failures


class PhaseMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    @property
    def phase(self) -> Phase:
        """The current phase, read from ``self._scene.document.phase`` —
        ``contracts.SceneDocument`` already carries this field, so orchestration is not a
        second source of truth for it."""
        return self._scene.document.phase

    def can_promote(self) -> tuple[bool, tuple[AcceptanceResult, ...]]:
        """Whether this phase's acceptance queries all pass against live geometry right now.

        Returns every result, not just the failures, so a caller can show what passed too.
        The boolean is derived from the results rather than computed beside them — ``False``
        with every result ``passed`` would itself be a bug in whatever computed it.

        Evaluated over the **whole scene**, not the recent changes: a promotion asks "is this
        ready to hand off", and scoping it to what changed lately would let a defect
        introduced early survive every later check. Promotion happens a handful of times per
        run; the per-operation check (``reporting._new_problems``) is the one that has to be
        cheap.
        """
        engine = getattr(self._scene, "engine", None)
        phase = self.phase
        if engine is None:
            return False, (
                AcceptanceResult(
                    query_id=f"{phase.value}.geometry_reachable",
                    passed=False,
                    subject="(scene)",
                    actual=0.0,
                    expected=1.0,
                    reason="this scene exposes no engine, so nothing can be measured",
                    suggested_operation="",
                ),
            )

        objects = tuple(sorted(engine.list_objects()))
        pairs: tuple[tuple[str, str], ...] = ()
        if phase is not Phase.BLOCKOUT and objects:
            try:
                pairs = self._promotion_index(engine).all_pairs(VISUAL_GAP_MAX)
            except Exception:  # noqa: BLE001 — a broken index must not wedge the gate
                pairs = ()
        joinery = tuple(
            intent for op in self._scene.document.operations for intent in op.joinery
        )

        results = evaluate_phase(engine, phase, objects, pairs, joinery)
        return all(r.passed for r in results), results

    def _promotion_index(self, engine) -> NeighbourIndex:
        """The same maintained BVH ``reporting`` uses, when there is one.

        Sharing it matters: two indices over one engine is two places invalidation can be
        got wrong, and a stale ``AABB`` is a silent wrong answer rather than a loud one.
        """
        neighbours = getattr(self, "_index", None)
        if neighbours is None or getattr(self, "_index_engine", None) is not engine:
            self._index_engine = engine
            self._index = NeighbourIndex(engine)
        return self._index

    def promote(self) -> Phase:
        """Advance to the next phase in :data:`contracts.PHASE_ORDER`, or refuse.

        - :class:`ValueError` if the current phase is already :attr:`contracts.Phase.POLISH`
          — there is no phase after it.
        - :class:`PromotionRefused` (also a ``ValueError``) unless every acceptance query
          passes. There is no parameter that overrides this, by design: ADR-012 removed the
          override rather than discouraging it, and a ``force`` keyword left in place —
          even defaulting to ``False`` — is the escape hatch one keyword away for any agent
          that reads the signature.
        - Only ever moves one step. There is no parameter naming a target phase, so "skip a
          phase" is structurally unreachable rather than merely refused.

        The transition is recorded in the operation log ``scene`` already keeps — reusing its
        existing subscriber notification rather than inventing a second audit channel — and
        carries the query ids that were checked, so an operator reviewing the run later can
        see what a phase was held to rather than only that it moved.
        """
        current_phase = self.phase
        index = PHASE_ORDER.index(current_phase)
        if index == len(PHASE_ORDER) - 1:
            raise ValueError(
                f"{current_phase} is the last phase in PHASE_ORDER; there is nothing to "
                "promote to"
            )

        can, results = self.can_promote()
        if not can:
            raise PromotionRefused(
                current_phase, tuple(r for r in results if not r.passed)
            )

        new_phase = PHASE_ORDER[index + 1]
        promotion_op = Operation(
            op_id=(
                f"phase_promotion-{current_phase.value}-{new_phase.value}-"
                f"{uuid.uuid4().hex[:8]}"
            ),
            kind="phase_promotion",
            phase=new_phase.value,
            author="orchestrator",
            params={
                "from": current_phase.value,
                "to": new_phase.value,
                "checked": tuple(r.query_id for r in results),
            },
        )
        # Promotion goes through the same write path as anything else, which means it needs
        # the live lease if one is held; without that the real Scene rejects it and promote()
        # cannot complete at all.
        self._scene.apply(promotion_op, lease=self._scene.document.active_lease)
        self._scene.document.phase = new_phase
        return new_phase

    def tools_for(self, role: ToolRole) -> tuple[ToolSpec, ...]:
        """The tools ``role`` can actually call **right now**.

        Phase-filtered, which is the point: ADR-013 requires "what can I do now" and "what
        will actually be accepted" to be the same answer. A tool listed as available and then
        refused by ``authorize`` teaches an agent that refusals are noise, and it retries
        them.

        The registry is the real one — ``mcp_server``'s, built from the ``ToolSpec``\\ s each
        operation module declares beside its own operations. It arrives by injection at
        construction rather than by import, because ``ARCHITECTURE.md``'s dependency arrow
        runs ``scene → orchestration → mcp`` and importing ``mcp_server`` here would reverse
        it. The deferred import below is a fallback for callers constructed before the
        composition root passes one; it is function-local, so the module-level import graph
        stays acyclic.

        This replaced a hand-written table of 16 tool names, **none** of which matched any of
        the 29 real ones (``close_gap`` against the real ``close_visual_gap``), every one
        carrying an empty input schema (Gate B 4.4).
        """
        if role not in roles_for_phase(self.phase):
            return ()
        if self._registry is not None:
            return tuple(self._registry.get(role, ()))
        try:
            from mcp_server import tools_for as registry_tools_for

            return tuple(registry_tools_for(role))
        except Exception:  # noqa: BLE001 — no registry is "no tools", never a crash
            return ()
