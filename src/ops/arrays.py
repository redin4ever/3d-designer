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

from contracts import EngineProtocol, Operation, OperationResult, ToolError, Transform, Vec3

from .validation import validate_params

__all__ = ["array_along", "add_lod_chain", "add_modular_kit"]


def array_along(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Instance ``object_id`` along ``path`` at a regular ``spacing``, corners resampled.

    Required params: ``object_id`` (str, must already exist), ``path`` (list of >= 2
    ``Vec3``), ``spacing`` (float, > 0). Optional: ``keep_upright`` (bool, default
    ``True``).

    Returns ``produced_objects`` naming every instance, in path order. The source object
    itself is left untouched — it is the caller's prototype, not a transient — so it is not
    part of ``produced_objects``.
    """
    params = validate_params("array_along", op.params)
    object_id = params["object_id"]
    path = list(params["path"])
    spacing = params["spacing"]
    keep_upright = params.get("keep_upright", True)

    if not engine.exists(object_id):
        raise ToolError(
            "ops.unknown_target",
            f"array_along: object {object_id!r} does not exist",
            "create the prototype object before arraying it",
        )

    corners = list(path[1:-1])
    produced = engine.array_along_curve(
        object_id,
        path,
        spacing,
        keep_upright=keep_upright,
        extra_points=corners,
        name_template=f"{op.op_id}_i{{index:03d}}",
    )

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))


def add_lod_chain(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Progressively simpler copies of ``object_id`` at each ratio in ``ratios``.

    Required params: ``object_id`` (str, must already exist), ``ratios`` (non-empty
    sequence of floats in ``(0, 1]``, first element ``1.0``).

    Level 0 is a plain duplicate — never decimated, even at "ratio 1.0" — so it stays the
    exact hero mesh. Every later level is duplicated fresh from the hero (not chained from
    the previous level) and decimated to its own ratio, which is what keeps the sequence
    strictly decreasing rather than compounding rounding error level over level.

    Returns ``produced_objects``, one id per ratio, in the same order as ``ratios``.
    """
    params = validate_params("add_lod_chain", op.params)
    object_id = params["object_id"]
    ratios = params["ratios"]

    if not engine.exists(object_id):
        raise ToolError(
            "ops.unknown_target",
            f"add_lod_chain: object {object_id!r} does not exist",
            "create the hero mesh before building a LOD chain from it",
        )

    produced = []
    for i, ratio in enumerate(ratios):
        name = f"{op.op_id}_lod{i:02d}"
        new_id = engine.duplicate(object_id, name)
        if i > 0:
            engine.decimate(new_id, ratio)
        produced.append(new_id)

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))


def add_modular_kit(engine: EngineProtocol, op: Operation) -> OperationResult:
    """``count_x`` by ``count_y`` grid-aligned tiling pieces, each ``piece_size``, on a
    ``grid_size`` grid starting at ``origin`` (default the world origin).

    Every piece's minimum corner sits at an exact multiple of ``grid_size`` from
    ``origin`` — the seam every neighbouring piece also snaps to.

    Returns ``produced_objects``, ``count_x * count_y`` pieces.
    """
    params = validate_params("add_modular_kit", op.params)
    grid_size = params["grid_size"]
    piece_size = params["piece_size"]
    count_x, count_y = params["count_x"], params["count_y"]
    origin = params.get("origin", Vec3())

    produced = []
    for iy in range(count_y):
        for ix in range(count_x):
            min_corner = Vec3(origin.x + ix * grid_size, origin.y + iy * grid_size, origin.z)
            centre = min_corner + Vec3(piece_size.x / 2.0, piece_size.y / 2.0, piece_size.z / 2.0)
            name = f"{op.op_id}_piece_{iy:02d}_{ix:02d}"
            pid = engine.create_primitive(name, "cube", piece_size, Transform(translation=centre))
            produced.append(pid)

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))
