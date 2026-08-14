"""Opening-aware façade rib layout."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_facade_ribs"]


def add_facade_ribs(engine: EngineProtocol, op: Operation) -> OperationResult:
    raise NotImplementedError("add_facade_ribs is not implemented")
