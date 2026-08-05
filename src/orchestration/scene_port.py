"""``ScenePort`` — the slice of the future ``src/scene`` module's public interface that
``orchestration`` depends on.

``src/scene`` is itself still a throwing stub in the making (``.pipeline/modules.json``
lists it "planned" — there is nothing real to import yet). This is orchestration's own
working assumption about the shape it will present: four methods, named directly in this
module's brief (``apply``, ``document``, ``undo``, ``subscribe``), kept here, typed,
rather than scattered as bare ``Any`` through every signature that touches ``scene``.

This is NOT a frozen contract — it lives in ``src/orchestration/`` because Rule 5
reserves ``src/contracts/`` for the main agent. If ``scene``'s real interface lands
differently, this is the one place to reconcile it (see this task's ``contractRequests``
output and ``.pipeline/contract-requests.json``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contracts import Operation, OperationResult, SceneDocument

__all__ = ["ScenePort"]


@runtime_checkable
class ScenePort(Protocol):
    """Structural — a real ``scene`` module, and any test double, satisfy this by shape
    alone, with no inheritance required (``@runtime_checkable``)."""

    def apply(self, op: Operation) -> OperationResult:
        """Append ``op`` to the operation log and evaluate it against the live engine."""
        ...

    def document(self) -> SceneDocument:
        """The live scene document — phase, head, the operation log, and
        ``active_lease``, the one field the write lock is held in
        (``contracts.WriteLease``'s own docstring)."""
        ...

    def undo(self, steps: int = 1) -> None: ...

    def subscribe(self, listener: object) -> None:
        """Register a listener for ``contracts.SceneChangeEvent``. ``scene`` never
        imports ``viewer``; this is the arrow that lets a change reach it anyway."""
        ...
