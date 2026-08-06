"""``add_staircase`` — a straight run of treads at a given rise, run and width.

Deliberately produces only the treads, named and world-measurable, rather than one joined
staircase mesh — a later ``ends_at`` or ``flush_with`` constraint (a railing's posts, most
commonly) needs to reference one tread's own edge, not an opaque combined shape with no
addressable parts.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult, Vec3

from ._geom import box_mesh
from .validation import validate_params

__all__ = ["add_staircase"]


def add_staircase(engine: EngineProtocol, op: Operation) -> OperationResult:
    """``treads`` treads, each rising ``rise`` and running ``run``, ``width`` wide,
    starting at ``origin`` (default the world origin — tread 0's rise is measured from
    there).

    Each tread is built as a solid block reaching down to ``origin.z`` — tread ``i``'s top
    surface therefore sits at exactly ``origin.z + (i + 1) * rise``, which is what makes
    both "each tread is one rise above the one below" and "the highest tread is
    ``treads * rise`` up" hold simultaneously and exactly, on the built geometry's own
    world bounds.

    Returns ``produced_objects`` naming exactly the treads, in climb order:
    ``f"{op.op_id}_tread_{i:03d}"`` for ``i`` in ``range(treads)``, tread 0 the lowest.
    """
    params = validate_params("add_staircase", op.params)
    treads, rise, run, width = (
        params["treads"], params["rise"], params["run"], params["width"]
    )
    origin = params.get("origin", Vec3())

    produced = []
    for i in range(treads):
        mins = Vec3(origin.x + i * run, origin.y - width / 2.0, origin.z)
        maxs = Vec3(
            origin.x + (i + 1) * run, origin.y + width / 2.0, origin.z + (i + 1) * rise
        )
        verts, faces = box_mesh(mins, maxs)
        tread_id = engine.create_mesh(f"{op.op_id}_tread_{i:03d}", verts, faces)
        produced.append(tread_id)

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))
