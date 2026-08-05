"""``add_primitive`` — the one typed, validated way to place a single primitive mesh.

Not the vocabulary agents are meant to reach for by default (ADR-004: a railing takes ~140
raw primitive calls and drift accumulates across every one) — but the other eight
operations in this package are themselves built from primitives, and roughing out a volume
before applying named operations to it still needs one typed, acceptance-checked way to
place a single primitive. This is that one way, not a reopened escape hatch back to
``add_cube``/``move``/``rotate``.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_primitive"]

_NOT_IMPLEMENTED = "ops.{name}: not implemented"


def add_primitive(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Create one named, validated primitive mesh.

    Required params: ``object_id`` (str), ``kind`` (one of cube|cylinder|sphere|plane|cone|
    torus, per ``contracts.EngineProtocol.create_primitive``), ``size`` (``Vec3``, every
    component > 0). Optional: ``transform`` (``Transform``).

    Must call ``validate_params("add_primitive", op.params)`` before touching the engine —
    a zero or negative size component must never reach ``engine.create_primitive`` to fail
    there as an opaque engine error instead of a named ``ToolError``.

    Returns ``produced_objects == (created_id,)`` where ``created_id`` is whatever
    ``engine.create_primitive`` actually returned — which may differ from the requested
    ``object_id`` if that id was already taken (see ``FakeEngine._unique``).
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_primitive"))
