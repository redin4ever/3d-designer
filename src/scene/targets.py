"""Which objects an operation is allowed to name (F-010, Gate B 5.2 — "reject where we
can, survive where we can't").

Split out of ``document.py`` rather than added to it: ``apply`` was already 130 lines, and
this is a distinct decision — *can this operation ever be re-run?* — taken once, before
anything else happens. ``.claude/rules/modularity.md``'s first and best seam.

The rule exists because geometry is generated from the log, from nothing, every time
(ADR-002). ``replay`` starts at ``engine.reset()``, so an operation whose target no logged
operation produced has nothing to act on the second time round. Recorded once, it made
every later ``undo``/``redo``/``rollback_to`` in the session raise — the reported failure
was ``EngineError: no object named 'bad_hole'`` from inside ``replay``'s handler loop,
three operations after the mistake and with no way back.

Objects that were in the engine when the ``Scene`` was constructed are legitimate targets.
``build_app(reset_scene=False)`` — "open an existing ``.blend`` and work on it" — is a
supported workflow, and rejecting its geometry would refuse the workflow rather than the
mistake. They are recorded here as such; what they *cannot* do is come back after a
rebuild, which is the other half's problem (see ``replay_report.py``).
"""

from __future__ import annotations

from typing import Iterable, Sequence

from contracts import Operation, RuleError

__all__ = ["UNKNOWN_TARGET_RULE", "TargetLedger"]

UNKNOWN_TARGET_RULE = "scene.unknown_target"
"""Named, so an agent is told which rule broke rather than handed a traceback three
operations later (Gate A 4.2)."""


class TargetLedger:
    """Every object id an operation may legitimately act upon.

    Two sources, and only two: what the engine held when this scene was constructed, and
    what the applied operations have produced. Deliberately *not* "what the engine holds
    right now" — that set includes anything raw code created behind the log's back, and
    accepting those is how an unreplayable operation gets into the log in the first place.
    """

    __slots__ = ("_present_at_construction", "_known")

    def __init__(self, present_at_construction: Iterable[str]) -> None:
        self._present_at_construction = frozenset(present_at_construction)
        self._known: set[str] = set(self._present_at_construction)

    @property
    def known(self) -> frozenset[str]:
        return frozenset(self._known)

    def record(self, produced: Iterable[str]) -> None:
        """Add what an operation just made. O(1) per id — the common path, taken on every
        successful ``apply``."""
        self._known.update(produced)

    def rebuild(self, operations: Sequence[Operation], head: int) -> None:
        """Recompute from the log after the head moved.

        O(head), and called only when the head moves *backwards* or the log is rebuilt —
        which already costs a replay of the same length, so this adds no new order of
        growth to anything. Undo genuinely removes objects, and a ledger that kept
        believing in them would wave through an operation that cannot run.
        """
        self._known = set(self._present_at_construction)
        for op in operations[:head]:
            self._known.update(op.produced_objects)

    def check(self, op: Operation) -> None:
        """Raise unless every id in ``op.target_objects`` is one this scene can rebuild.

        Raises :class:`contracts.RuleError` rather than returning a failed
        ``OperationResult``, matching the other two pre-append refusals in ``apply``
        (duplicate ``op_id``, opaque-without-a-snapshot): nothing ran, so there is no
        result to report, and ``RuleError`` is the one shape the boundary in
        ``app/handlers.py`` already turns into an agent-readable failure.
        """
        unknown = [t for t in op.target_objects if t not in self._known]
        if not unknown:
            return
        raise RuleError(
            rule=UNKNOWN_TARGET_RULE,
            detail=(
                f"operation {op.op_id!r} ({op.kind}) targets "
                f"{', '.join(repr(t) for t in unknown)}, which no operation in this scene "
                "produced and which was not present when the scene was opened"
            ),
            suggestion=(
                "name an object this scene made, or open the file with "
                "reset_scene=False so the geometry already in it is on the record. "
                "Recording this operation would make every later undo fail, because "
                "geometry is rebuilt from the log and this target would not exist."
            ),
        )
