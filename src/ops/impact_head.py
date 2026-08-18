"""Semantic construction of a fitted dual-strike impact head."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_impact_head"]


def add_impact_head(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("impact-head geometry is implemented after its contract tests")
