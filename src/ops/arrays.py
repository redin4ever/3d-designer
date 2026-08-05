"""``array_along``, ``add_lod_chain``, ``add_modular_kit`` — the general-purpose repeat,
simplify and tile operations.

``array_along`` is the general instancing primitive ``add_railing`` itself is built on top
of (``contracts.ModifierOps.array_along_curve``) — exposed directly for the many cases that
are just "repeat this along a path" with no railing-specific vocabulary (plumb balusters, a
top rail, a clear-gap spacing rule) attached. ``add_lod_chain`` and ``add_modular_kit`` are
unrelated to arraying geometrically, but share this file because all three, unlike every
other operation in this package, produce a *set* of related objects from one call rather
than one object from one call — the seam this file is split along.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["array_along", "add_lod_chain", "add_modular_kit"]

_NOT_IMPLEMENTED = "ops.{name}: not implemented"


def array_along(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Instance ``object_id`` along ``path`` at a regular ``spacing``, corners resampled.

    Required params: ``object_id`` (str, must already exist), ``path`` (list of >= 2
    ``Vec3``), ``spacing`` (float, > 0, must fit at least once along the path's own arc
    length — a spacing longer than the path is a named ``ToolError``, not a silent
    single-instance result). Optional: ``keep_upright`` (bool, default ``True`` — see
    ``contracts.ModifierOps.array_along_curve``).

    Must call ``validate_params("array_along", op.params)`` first.

    Returns ``produced_objects`` naming every instance, in path order.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="array_along"))


def add_lod_chain(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Progressively simpler copies of ``object_id`` at each ratio in ``ratios``.

    Required params: ``object_id`` (str, must already exist), ``ratios`` (non-empty
    sequence of floats in ``(0, 1]``, first element ``1.0`` — level 0 is the hero mesh
    itself, unmodified, not a 100%-ratio decimation of it).

    Each subsequent level must have **strictly fewer** triangles than the one before it —
    a chain with two equal-weight levels defeats the reason a LOD chain exists at all,
    which is to spend less at distance for zero perceptible loss up close.

    Returns ``produced_objects``, one id per ratio, in the same order as ``ratios``.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_lod_chain"))


def add_modular_kit(engine: EngineProtocol, op: Operation) -> OperationResult:
    """``count_x`` by ``count_y`` grid-aligned tiling pieces, each ``piece_size``, on a
    ``grid_size`` grid starting at ``origin`` (default the world origin).

    Required params: ``object_id`` (str), ``grid_size`` (float, > 0), ``piece_size``
    (``Vec3``), ``count_x`` (int, >= 1), ``count_y`` (int, >= 1). Optional: ``origin``
    (``Vec3``, default ``Vec3()``).

    Every produced piece's world bounds must land on the grid within
    ``contracts.EPSILON`` on x and y — a piece off the grid by even a fraction of a
    millimetre leaves a visible seam or overlap at that edge, because its neighbour is
    still placed exactly on-grid.

    Returns ``produced_objects``, ``count_x * count_y`` pieces.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_modular_kit"))
