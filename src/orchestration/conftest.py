"""Local pytest fixtures for ``orchestration``'s own test suite. Not part of the public
interface — nothing outside this directory's ``*_test.py`` files should import from here.

``FakeScene`` stands in for the future ``src/scene`` module, which is itself still a
throwing stub in the making (``.pipeline/modules.json`` lists it "planned" — there is
nothing real to import). It implements exactly the four methods this module's brief names
as orchestration's dependency on scene — ``apply``, ``document``, ``undo``, ``subscribe``
(``ScenePort`` in ``scene_port.py``) — backed by a real ``contracts.SceneDocument``
rather than recording calls, so a test can assert on real document state (head, phase,
the operation log, ``active_lease``) instead of on which methods were called. Same
reasoning as ``testing.FakeEngine``'s own docstring, one layer down: a double that only
records calls lets a wrong implementation pass because the test asserts on the
conversation rather than the outcome.
"""

from __future__ import annotations

from typing import Callable

import pytest

from contracts import Operation, OperationResult, SceneDocument, Vec3
from testing import FakeEngine


class FakeScene:
    """A minimal, real, in-memory stand-in for ``src/scene``'s public surface.

    **This double must match the real `Scene`, method for method and property for
    property.** It previously declared ``apply(self, op)`` with no lease and exposed no
    ``engine`` — matching an incomplete ``ScenePort`` rather than the real thing — and that
    agreement with the wrong side is exactly why a P0 (``perform`` never forwarding the
    lease, so every mutating call failed) passed three test suites unnoticed.
    """

    def __init__(self) -> None:
        self._doc = SceneDocument()
        self.subscribers: list[Callable[..., None]] = []
        self._engine = FakeEngine()
        self.applied_with_lease: list[object] = []

    def apply(self, op: Operation, *, lease: object | None = None) -> OperationResult:
        # Record it so a test can assert the lease actually arrived — the real Scene
        # rejects the call without it.
        self.applied_with_lease.append(lease)
        self._doc.append(op, snapshot_path="fake-snapshot" if op.opaque else "")

        # Actually create the geometry this operation claims to produce. The real Scene
        # does, and `perform` now measures what an operation touched — so a double that
        # reports objects it never created makes every measurement silently empty while
        # the suite reads as green.
        produced = tuple(op.produced_objects) or ((op.params.get("object_id"),) if op.params.get("object_id") else ())
        created = []
        for object_id in produced:
            if object_id and not self._engine.exists(object_id):
                created.append(self._engine.create_primitive(object_id, "cube", Vec3(1.0, 1.0, 1.0)))
            elif object_id:
                created.append(object_id)

        return OperationResult(
            op_id=op.op_id,
            ok=True,
            produced_objects=tuple(created),
            modified_objects=op.target_objects,
        )

    @property
    def engine(self) -> FakeEngine:
        """Present because the real `Scene` exposes it, and because `perform` needs it to
        run real measurements. A double missing it makes `perform` silently fall back to
        no measurements while the suite stays green."""
        return self._engine

    @property
    def document(self) -> SceneDocument:
        return self._doc

    def undo(self, steps: int = 1) -> None:
        self._doc.set_head(max(0, self._doc.head - steps))

    def subscribe(self, listener: Callable[..., None]) -> None:
        self.subscribers.append(listener)


@pytest.fixture
def scene() -> FakeScene:
    """A fresh scene for every test. Orchestration tests must never share mutable state
    across tests, or a lease/phase left over from one test would silently change the
    next test's starting conditions."""
    return FakeScene()
