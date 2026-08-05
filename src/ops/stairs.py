"""``add_staircase`` — a straight run of treads at a given rise, run and width.

Deliberately produces only the treads, named and world-measurable, rather than one joined
staircase mesh — a later ``ends_at`` or ``flush_with`` constraint (a railing's posts, most
commonly) needs to reference one tread's own edge, not an opaque combined shape with no
addressable parts.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_staircase"]

_NOT_IMPLEMENTED = "ops.{name}: not implemented"


def add_staircase(engine: EngineProtocol, op: Operation) -> OperationResult:
    """``treads`` treads, each rising ``rise`` and running ``run``, ``width`` wide,
    starting at ``origin`` (default the world origin — tread 0's rise is measured from
    there).

    Required params: ``object_id`` (str), ``treads`` (int, >= 1), ``rise`` (float, > 0),
    ``run`` (float, > 0), ``width`` (float, > 0). Optional: ``origin`` (``Vec3``, default
    ``Vec3()``).

    Must call ``validate_params("add_staircase", op.params)`` first — ``treads == 0`` is a
    request for a staircase that goes nowhere, not an empty-but-valid result.

    Every tread's own top surface must land exactly ``rise`` above the tread below it, and
    the top of the highest tread must sit at exactly ``treads * rise`` above ``origin`` —
    both checked by the test suite on the built geometry's *world bounds*, never on the
    ``rise``/``treads`` parameters handed in, because a handler can validate a parameter
    and still build the wrong thing.

    Returns ``produced_objects`` naming exactly the treads, in climb order:
    ``f"{op.op_id}_tread_{i:03d}"`` for ``i`` in ``range(treads)``, tread 0 the lowest.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_staircase"))
