"""Semantic roof-window and wall-sign operations."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_roof_window", "add_wall_sign"]


def add_roof_window(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("add_roof_window is not implemented")


def add_wall_sign(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("add_wall_sign is not implemented")
