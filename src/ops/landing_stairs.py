"""``add_staircase_to_landing`` — derive a supported stair from a live landing."""

from __future__ import annotations

from contracts import EPSILON, EngineProtocol, Operation, OperationResult, ToolError, Vec3

from ._geom import oriented_box_between
from .validation import validate_params

__all__ = ["add_staircase_to_landing"]


def add_staircase_to_landing(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build thin treads and two side stringers ending exactly at ``landing_id``.

    The caller chooses the bottom-front centre and tread count. The operation reads the
    landing's live bounds, finds the near edge on the line to its centre, and derives the
    direction, run and rise. No camera-space or fixed-axis guess enters the geometry.
    """
    p = validate_params("add_staircase_to_landing", op.params)
    prefix = p["object_id"]
    landing_id = p["landing_id"]
    if not engine.exists(landing_id):
        raise ToolError(
            "ops.unknown_landing",
            f"add_staircase_to_landing: landing {landing_id!r} does not exist",
            "pass an existing floor, porch or deck object id",
        )

    start = p["start"]
    bounds = engine.world_bounds(landing_id)
    landing_top = bounds.maximum.z
    if landing_top <= start.z + EPSILON:
        raise ToolError(
            "ops.landing_not_above_start",
            f"landing top {landing_top:.4g}m is not above stair start {start.z:.4g}m",
            "choose a lower start or an elevated landing",
        )
    if (
        bounds.minimum.x - EPSILON <= start.x <= bounds.maximum.x + EPSILON
        and bounds.minimum.y - EPSILON <= start.y <= bounds.maximum.y + EPSILON
    ):
        raise ToolError(
            "ops.start_inside_landing",
            "the stair start lies inside the landing footprint, so there is no approach run",
            "place start outside the landing footprint",
        )

    center = (bounds.minimum + bounds.maximum) * 0.5
    toward = Vec3(center.x - start.x, center.y - start.y, 0.0)
    if toward.length() <= EPSILON:
        raise ToolError(
            "ops.degenerate_stair_run",
            "the stair start and landing centre have no horizontal separation",
            "move the start outside the landing footprint",
        )
    forward = toward.normalized()
    lateral = Vec3(-forward.y, forward.x, 0.0)
    half_x = (bounds.maximum.x - bounds.minimum.x) / 2.0
    half_y = (bounds.maximum.y - bounds.minimum.y) / 2.0
    edge_distances = []
    if abs(forward.x) > EPSILON:
        edge_distances.append(half_x / abs(forward.x))
    if abs(forward.y) > EPSILON:
        edge_distances.append(half_y / abs(forward.y))
    edge_distance = min(edge_distances)
    attach = Vec3(
        center.x - forward.x * edge_distance,
        center.y - forward.y * edge_distance,
        landing_top,
    )

    total_run = Vec3(attach.x - start.x, attach.y - start.y, 0.0).length()
    treads = p["treads"]
    run = total_run / treads
    rise = (landing_top - start.z) / treads
    width = p["width"]
    tread_thickness = p["tread_thickness"]
    stringer_width = p["stringer_width"]
    stringer_depth = p["stringer_depth"]
    if tread_thickness >= rise:
        raise ToolError(
            "ops.tread_too_thick",
            f"tread thickness {tread_thickness:.4g}m must be below derived rise {rise:.4g}m",
            "reduce tread_thickness or use fewer treads",
        )

    produced = []
    for i in range(treads):
        front = start + forward * (i * run)
        back = start + forward * ((i + 1) * run)
        top_z = start.z + (i + 1) * rise
        tread_id = engine.create_mesh(
            f"{prefix}_tread_{i:03d}",
            *_tread_mesh(front, back, lateral, width, top_z, tread_thickness),
        )
        produced.append(tread_id)

    support_offset = width / 2.0 - stringer_width / 2.0
    support_z0 = start.z + rise - tread_thickness - stringer_depth / 2.0
    support_z1 = landing_top - tread_thickness - stringer_depth / 2.0
    for side, sign in (("left", 1.0), ("right", -1.0)):
        a = start + forward * (run / 2.0) + lateral * (sign * support_offset)
        b = attach - forward * (run / 2.0) + lateral * (sign * support_offset)
        a = Vec3(a.x, a.y, support_z0)
        b = Vec3(b.x, b.y, support_z1)
        produced.append(
            engine.create_mesh(
                f"{prefix}_stringer_{side}",
                *oriented_box_between(a, b, stringer_width, stringer_depth),
            )
        )

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))


def _tread_mesh(
    front: Vec3,
    back: Vec3,
    lateral: Vec3,
    width: float,
    top_z: float,
    thickness: float,
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    half = lateral * (width / 2.0)
    bottom_z = top_z - thickness
    bottom = [
        Vec3(front.x - half.x, front.y - half.y, bottom_z),
        Vec3(back.x - half.x, back.y - half.y, bottom_z),
        Vec3(back.x + half.x, back.y + half.y, bottom_z),
        Vec3(front.x + half.x, front.y + half.y, bottom_z),
    ]
    verts = bottom + [p + Vec3(0.0, 0.0, thickness) for p in bottom]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return verts, faces
