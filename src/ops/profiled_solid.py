"""Section-based solid construction (implementation follows its contract tests)."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_profiled_solid"]


def add_profiled_solid(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("profiled solid geometry is not implemented")
