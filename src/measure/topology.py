"""Stub — the six single-object defect detectors. See ``src/measure/README.md``.

These are genuinely different problems with different repairs (``contracts.DefectClass``
docstrings are explicit about this); treating them as one "fix the gaps" step is the most
common mistake in this domain. Nothing below is implemented yet — every function raises.

Pure: read-only over ``engine.snapshot(object_id)``. No mutating engine call.
"""

from __future__ import annotations

from contracts import EPSILON, Defect, EngineProtocol

__all__ = [
    "find_boundary_holes",
    "find_non_manifold_edges",
    "find_non_manifold_vertices",
    "find_loose_or_duplicate",
    "find_flipped_normals",
    "find_unapplied_transforms",
]


def find_boundary_holes(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per closed loop of edges each bounding exactly one face.

    ``DefectClass.BOUNDARY_HOLE`` — repair is to triangulate the loop.
    """
    raise NotImplementedError("measure.find_boundary_holes: not implemented")


def find_non_manifold_edges(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per edge with three or more incident faces.

    ``DefectClass.NON_MANIFOLD_EDGE`` — repair is to split the fan.
    """
    raise NotImplementedError("measure.find_non_manifold_edges: not implemented")


def find_non_manifold_vertices(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per vertex whose incident faces form more than one fan — two
    cones touching at a point.

    ``DefectClass.NON_MANIFOLD_VERTEX`` — repair is to duplicate the vertex, one copy per
    fan.
    """
    raise NotImplementedError("measure.find_non_manifold_vertices: not implemented")


def find_loose_or_duplicate(
    engine: EngineProtocol, object_id: str, tolerance: float = EPSILON
) -> tuple[Defect, ...]:
    """One :class:`Defect` per vertex/edge with no attached face, and one per coincident
    vertex not welded to its representative (vertices within ``tolerance`` of an
    earlier-indexed vertex are duplicates of it).

    ``DefectClass.LOOSE_OR_DUPLICATE``.
    """
    raise NotImplementedError("measure.find_loose_or_duplicate: not implemented")


def find_flipped_normals(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per face whose winding is inconsistent with its neighbours.

    ``DefectClass.FLIPPED_NORMAL`` — invisible in solid shading with backface culling off,
    and it breaks booleans and exports.
    """
    raise NotImplementedError("measure.find_flipped_normals: not implemented")


def find_unapplied_transforms(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """A single :class:`Defect` if the object carries non-unit scale not baked into mesh
    data (see :meth:`contracts.Transform.has_unapplied_scale`); empty otherwise.

    ``DefectClass.UNAPPLIED_TRANSFORM`` — looks correct in the viewport and silently
    corrupts bevel width, boolean results and physics.
    """
    raise NotImplementedError("measure.find_unapplied_transforms: not implemented")
