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

from contracts import Operation, OperationResult, SceneDocument


class FakeScene:
    """A minimal, real, in-memory stand-in for ``src/scene``'s eventual public surface."""

    def __init__(self) -> None:
        self._doc = SceneDocument()
        self.subscribers: list[Callable[..., None]] = []

    def apply(self, op: Operation) -> OperationResult:
        self._doc.append(op, snapshot_path="fake-snapshot" if op.opaque else "")
        return OperationResult(
            op_id=op.op_id,
            ok=True,
            produced_objects=op.produced_objects,
            modified_objects=op.target_objects,
        )

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
