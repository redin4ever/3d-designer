"""Local pytest fixtures for ``mcp``'s own test suite. Not part of the public interface —
nothing outside this directory's ``*_test.py`` files should import from here.

``FakeScene`` mirrors ``orchestration/conftest.py``'s own double (it cannot be imported
from there — it is private to that package's test suite, per that module's own
``CLAUDE.md`` boundary rules). Same reasoning as ``testing.FakeEngine``'s docstring: a
double backed by a real ``contracts.SceneDocument`` lets a test assert on real state
(``document().head``, the operation log, ``active_lease``) instead of on which methods
were called, so a wrong ``dispatch()`` implementation cannot pass by asserting on the
conversation rather than the outcome.
"""

from __future__ import annotations

from typing import Callable

import pytest
from contracts import Operation, OperationResult, Phase, SceneDocument
from orchestration import Orchestrator


class FakeScene:
    """A minimal, real, in-memory stand-in for ``src/scene``'s public surface
    (``orchestration.ScenePort``)."""

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

    @property
    def document(self) -> SceneDocument:
        return self._doc

    def undo(self, steps: int = 1) -> None:
        self._doc.set_head(max(0, self._doc.head - steps))

    def subscribe(self, listener: Callable[..., None]) -> None:
        self.subscribers.append(listener)


@pytest.fixture
def fake_scene() -> FakeScene:
    """A fresh scene for every test — a lease or logged operation left over from one test
    must never change the next test's starting conditions."""
    return FakeScene()


@pytest.fixture
def orchestrator(fake_scene: FakeScene) -> Orchestrator:
    return Orchestrator(fake_scene)


@pytest.fixture
def write_lease(orchestrator: Orchestrator):
    """A live write lease, granted in the BLOCKOUT phase — every dispatch test that
    exercises a successful mutating call needs one already held."""
    return orchestrator.acquire(holder="test-writer", phase=Phase.BLOCKOUT)
