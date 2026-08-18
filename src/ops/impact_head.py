"""``add_impact_head`` — a fitted dual-strike hard-surface assembly.

The operation owns the relationships that primitive stacking cannot: armor follows one body,
both striking faces share one load path, and intentional sockets carry explicit insertion depth.
"""

from __future__ import annotations

import math

from contracts import EngineProtocol, Operation, OperationResult, Quat, Transform, Vec3

from .validation import validate_params

__all__ = ["add_impact_head"]


def _extrude_xz(
    centre: Vec3, width: float, height: float, depth: float, chamfer: float
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """Closed Y-extrusion of a flat-topped, corner-clipped X/Z profile."""
    hx, hz, hy = width / 2.0, height / 2.0, depth / 2.0
    profile = (
        (-hx + chamfer, -hz), (hx - chamfer, -hz),
        (hx, -hz + chamfer), (hx, hz - chamfer),
        (hx - chamfer, hz), (-hx + chamfer, hz),
        (-hx, hz - chamfer), (-hx, -hz + chamfer),
    )
    front = [Vec3(centre.x + x, centre.y - hy, centre.z + z) for x, z in profile]
    back = [Vec3(point.x, centre.y + hy, point.z) for point in front]
    vertices = front + back
    n = len(profile)
    faces: list[tuple[int, ...]] = [
        tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n)),
    ]
    faces.extend((i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n))
    return vertices, faces


def _chamfered_xy(
    centre: Vec3, width: float, depth: float, height: float, chamfer: float
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """Closed Z-extrusion of an eight-sided armor-plate plan."""
    hx, hy, hz = width / 2.0, depth / 2.0, height / 2.0
    ring = (
        (-hx + chamfer, -hy), (hx - chamfer, -hy),
        (hx, -hy + chamfer), (hx, hy - chamfer),
        (hx - chamfer, hy), (-hx + chamfer, hy),
        (-hx, hy - chamfer), (-hx, -hy + chamfer),
    )
    lower = [Vec3(centre.x + x, centre.y + y, centre.z - hz) for x, y in ring]
    upper = [Vec3(point.x, point.y, centre.z + hz) for point in lower]
    vertices = lower + upper
    n = len(ring)
    faces: list[tuple[int, ...]] = [
        tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n)),
    ]
    faces.extend((i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n))
    return vertices, faces


def _axis_x(engine: EngineProtocol, object_id: str, length: float, diameter: float, at: Vec3) -> str:
    rotation = Quat.from_axis_angle(Vec3(0.0, 1.0, 0.0), math.pi / 2.0)
    return engine.create_primitive(
        object_id, "cylinder", Vec3(diameter, diameter, length),
        Transform(translation=at, rotation=rotation),
    )


def _rim_x(engine: EngineProtocol, object_id: str, depth: float, diameter: float, at: Vec3) -> str:
    rotation = Quat.from_axis_angle(Vec3(0.0, 1.0, 0.0), math.pi / 2.0)
    return engine.create_primitive(
        object_id, "torus", Vec3(diameter, diameter, depth),
        Transform(translation=at, rotation=rotation),
    )


def add_impact_head(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build one body, fitted armor, two socketed strike stacks, and a handle socket."""
    p = validate_params("add_impact_head", op.params)
    prefix, origin = p["object_id"], p["origin"]
    width, depth, height = p["width"], p["depth"], p["height"]
    half_width, half_depth, half_height = width / 2.0, depth / 2.0, height / 2.0

    body_id = engine.create_mesh(
        f"{prefix}_body",
        *_extrude_xz(origin, width, height, depth, p["corner_chamfer"]),
    )

    plate_width = width - 2.0 * p["plate_inset"]
    plate_depth = depth - 2.0 * p["plate_inset"]
    plate_height = height - 2.0 * p["plate_inset"]
    plate_chamfer = min(p["corner_chamfer"], plate_width * 0.18, plate_depth * 0.18)
    top_id = engine.create_mesh(
        f"{prefix}_top_plate",
        *_chamfered_xy(
            Vec3(origin.x, origin.y, origin.z + half_height + p["plate_thickness"] / 2.0),
            plate_width, plate_depth, p["plate_thickness"], plate_chamfer,
        ),
    )
    cheek_chamfer = min(p["corner_chamfer"] * 0.65, plate_width * 0.18, plate_height * 0.18)
    front_id = engine.create_mesh(
        f"{prefix}_cheek_front",
        *_extrude_xz(
            Vec3(origin.x, origin.y - half_depth - p["plate_thickness"] / 2.0, origin.z),
            plate_width, plate_height, p["plate_thickness"], cheek_chamfer,
        ),
    )
    back_id = engine.create_mesh(
        f"{prefix}_cheek_back",
        *_extrude_xz(
            Vec3(origin.x, origin.y + half_depth + p["plate_thickness"] / 2.0, origin.z),
            plate_width, plate_height, p["plate_thickness"], cheek_chamfer,
        ),
    )

    produced = [body_id, top_id, front_id, back_id]
    for side, sign in (("left", -1.0), ("right", 1.0)):
        body_edge = origin.x + sign * half_width
        shoulder_x = body_edge + sign * (p["shoulder_depth"] - p["socket_depth"]) / 2.0
        shoulder_id = _axis_x(
            engine, f"{prefix}_shoulder_{side}",
            p["shoulder_depth"] + p["socket_depth"], p["shoulder_diameter"],
            Vec3(shoulder_x, origin.y, origin.z),
        )
        shoulder_outer = body_edge + sign * p["shoulder_depth"]
        collar_x = shoulder_outer + sign * p["collar_depth"] / 2.0
        collar_id = _axis_x(
            engine, f"{prefix}_collar_{side}", p["collar_depth"], p["collar_diameter"],
            Vec3(collar_x, origin.y, origin.z),
        )
        collar_outer = shoulder_outer + sign * p["collar_depth"]
        face_x = collar_outer + sign * p["face_depth"] / 2.0
        face_id = _axis_x(
            engine, f"{prefix}_face_{side}", p["face_depth"], p["face_diameter"],
            Vec3(face_x, origin.y, origin.z),
        )
        face_outer = collar_outer + sign * p["face_depth"]
        rim_id = _rim_x(
            engine, f"{prefix}_rim_{side}", p["rim_depth"],
            p["face_diameter"] + 2.0 * p["rim_overhang"],
            Vec3(face_outer, origin.y, origin.z),
        )
        produced.extend((shoulder_id, collar_id, face_id, rim_id))

    body_bottom = origin.z - half_height
    socket_length = p["handle_socket_depth"] + p["handle_collar_depth"]
    socket_id = engine.create_primitive(
        f"{prefix}_handle_socket", "cylinder",
        Vec3(p["handle_socket_diameter"], p["handle_socket_diameter"], socket_length),
        Transform(translation=Vec3(
            origin.x, origin.y,
            body_bottom + (p["handle_socket_depth"] - p["handle_collar_depth"]) / 2.0,
        )),
    )
    handle_collar_diameter = p["handle_socket_diameter"] + 2.0 * p["handle_collar_overhang"]
    handle_collar_id = engine.create_primitive(
        f"{prefix}_handle_collar", "torus",
        Vec3(handle_collar_diameter, handle_collar_diameter, p["handle_collar_depth"]),
        Transform(translation=Vec3(
            origin.x, origin.y, body_bottom - p["handle_collar_depth"] / 2.0,
        )),
    )
    produced.extend((socket_id, handle_collar_id))

    for object_id in produced:
        engine.bevel_edges(object_id, width=p["bevel_width"], segments=3)

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))
