"""``add_chimney`` — a complete masonry chimney and roof-junction assembly."""

from __future__ import annotations

import math

from contracts import EngineProtocol, Operation, OperationResult, Vec3

from ._geom import box_mesh
from .validation import validate_params

__all__ = ["add_chimney"]


def _ring(x: float, y: float, z: float, half_width: float, half_depth: float) -> list[Vec3]:
    return [
        Vec3(x - half_width, y - half_depth, z),
        Vec3(x + half_width, y - half_depth, z),
        Vec3(x + half_width, y + half_depth, z),
        Vec3(x - half_width, y + half_depth, z),
    ]


def _flashing_mesh(
    origin: Vec3, width: float, depth: float, overhang: float, height: float
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """A closed hollow apron: broad at the roof and tucked against the shaft above."""
    inner_w, inner_d = width / 2.0, depth / 2.0
    lower_outer = _ring(origin.x, origin.y, origin.z, inner_w + overhang, inner_d + overhang)
    lower_inner = _ring(origin.x, origin.y, origin.z, inner_w, inner_d)
    shoulder = overhang * 0.25
    upper_outer = _ring(
        origin.x, origin.y, origin.z + height, inner_w + shoulder, inner_d + shoulder
    )
    upper_inner = _ring(origin.x, origin.y, origin.z + height, inner_w, inner_d)
    vertices = lower_outer + lower_inner + upper_outer + upper_inner
    faces: list[tuple[int, ...]] = []
    for i in range(4):
        j = (i + 1) % 4
        faces.extend(
            (
                (i, j, 8 + j, 8 + i),
                (4 + i, 12 + i, 12 + j, 4 + j),
                (i, 4 + i, 4 + j, j),
                (8 + i, 8 + j, 12 + j, 12 + i),
            )
        )
    return vertices, faces


def _pipe_mesh(
    centre: Vec3,
    outer_radius: float,
    inner_radius: float,
    z_min: float,
    z_max: float,
    sides: int = 24,
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    outer_lower = [
        Vec3(
            centre.x + outer_radius * math.cos(2.0 * math.pi * i / sides),
            centre.y + outer_radius * math.sin(2.0 * math.pi * i / sides),
            z_min,
        )
        for i in range(sides)
    ]
    outer_upper = [Vec3(point.x, point.y, z_max) for point in outer_lower]
    inner_lower = [
        Vec3(
            centre.x + inner_radius * math.cos(2.0 * math.pi * i / sides),
            centre.y + inner_radius * math.sin(2.0 * math.pi * i / sides),
            z_min,
        )
        for i in range(sides)
    ]
    inner_upper = [Vec3(point.x, point.y, z_max) for point in inner_lower]
    vertices = outer_lower + outer_upper + inner_lower + inner_upper
    faces: list[tuple[int, ...]] = []
    for i in range(sides):
        j = (i + 1) % sides
        faces.extend(
            (
                (i, j, sides + j, sides + i),
                (2 * sides + i, 3 * sides + i, 3 * sides + j, 2 * sides + j),
                (i, 2 * sides + i, 2 * sides + j, j),
                (sides + i, sides + j, 3 * sides + j, 3 * sides + i),
            )
        )
    return vertices, faces


def _flue_centres(
    origin: Vec3, width: float, depth: float, crown_overhang: float, count: int
) -> list[Vec3]:
    along_y = depth >= width
    length = (depth if along_y else width) + 2.0 * crown_overhang
    pitch = length / count
    offsets = [-length / 2.0 + pitch * (i + 0.5) for i in range(count)]
    if along_y:
        return [Vec3(origin.x, origin.y + offset, 0.0) for offset in offsets]
    return [Vec3(origin.x + offset, origin.y, 0.0) for offset in offsets]


def add_chimney(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build a shaft, roof flashing, crown, and one or more rimmed flues.

    ``origin`` is the centre of the shaft footprint at its base. Every visible dimension
    is explicit; the operation only derives symmetric placement and the flashing taper.
    """
    p = validate_params("add_chimney", op.params)
    prefix, origin = p["object_id"], p["origin"]
    width, depth, shaft_height = p["width"], p["depth"], p["shaft_height"]

    shaft_vertices, shaft_faces = box_mesh(
        Vec3(origin.x - width / 2.0, origin.y - depth / 2.0, origin.z),
        Vec3(origin.x + width / 2.0, origin.y + depth / 2.0, origin.z + shaft_height),
    )
    shaft_id = engine.create_mesh(f"{prefix}_shaft", shaft_vertices, shaft_faces)
    flashing_id = engine.create_mesh(
        f"{prefix}_flashing",
        *_flashing_mesh(
            origin, width, depth, p["flashing_overhang"], p["flashing_height"]
        ),
    )

    crown_z = origin.z + shaft_height
    crown_overhang, crown_height = p["crown_overhang"], p["crown_height"]
    crown_id = engine.create_mesh(
        f"{prefix}_crown",
        *box_mesh(
            Vec3(
                origin.x - width / 2.0 - crown_overhang,
                origin.y - depth / 2.0 - crown_overhang,
                crown_z,
            ),
            Vec3(
                origin.x + width / 2.0 + crown_overhang,
                origin.y + depth / 2.0 + crown_overhang,
                crown_z + crown_height,
            ),
        ),
    )

    produced = [shaft_id, flashing_id, crown_id]
    flue_base = crown_z + crown_height
    flue_top = flue_base + p["flue_height"] - p["rim_height"]
    rim_top = flue_base + p["flue_height"]
    centres = _flue_centres(origin, width, depth, crown_overhang, p["flue_count"])
    inner_radius = p["flue_radius"] - p["flue_wall_thickness"]
    for index, centre in enumerate(centres):
        flue_id = engine.create_mesh(
            f"{prefix}_flue_{index:03d}",
            *_pipe_mesh(centre, p["flue_radius"], inner_radius, flue_base, flue_top),
        )
        rim_id = engine.create_mesh(
            f"{prefix}_flue_{index:03d}_rim",
            *_pipe_mesh(
                centre,
                p["flue_radius"] + p["rim_overhang"],
                inner_radius,
                flue_top,
                rim_top,
            ),
        )
        produced.extend((flue_id, rim_id))

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=tuple(produced))
