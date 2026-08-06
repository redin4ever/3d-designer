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

from contracts import EngineProtocol, Operation, OperationResult, SceneDocument

__all__ = ["ScenePort"]


@runtime_checkable
class ScenePort(Protocol):
    """Structural — a real ``scene`` module, and any test double, satisfy this by shape
    alone, with no inheritance required (``@runtime_checkable``)."""

    @property
    def engine(self) -> EngineProtocol:
        """The engine behind this scene, so measurements can run against real geometry.

        Added to close B-000. Without it ``reporting.perform`` had no route to geometry
        and emitted placeholder measurements, which meant the
        check-after-every-geometry-change loop — Gate A 3.1, in the user's own words, and
        ADR-005's core promise — was not actually running. Read-only access; nothing here
        mutates the scene.
        """
        ...

    def apply(
        self, op: Operation, *, lease: object | None = None, snapshot_path: str = ""
    ) -> OperationResult:
        """Append ``op`` to the operation log and evaluate it against the live engine.

        ``lease`` is the caller's proof it holds the single write lock. It is part of this
        signature because the real ``Scene.apply`` requires it once a lock is held — and an
        earlier version of this Protocol omitted it, so ``Orchestrator.perform`` called
        ``apply(op)`` and got ``LockContention`` against the lease it had just verified.
        Both test doubles matched the incomplete declaration, so three suites stayed green
        while every mutating call through the real agent path failed.
        """
        ...

    @property
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
