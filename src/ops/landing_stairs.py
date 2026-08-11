"""Landing-connected architectural stair. Implemented after its public tests are red."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_staircase_to_landing"]


def add_staircase_to_landing(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("add_staircase_to_landing")
