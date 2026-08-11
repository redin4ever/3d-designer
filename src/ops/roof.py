"""Semantic gable-roof construction. Implemented after the public tests are red."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_gable_roof"]


def add_gable_roof(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("add_gable_roof")
