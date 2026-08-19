"""``add_gable_roof`` — a detailed roof assembly derived from architectural dimensions."""

from __future__ import annotations

import math

from contracts import EngineProtocol, Operation, OperationResult, Vec3

from ._geom import oriented_box_between
from ._roof_trim import perimeter_trim_meshes
from .validation import validate_params

__all__ = ["add_gable_roof"]


def add_gable_roof(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build two exact-pitch slabs plus continuous ridge, rake and eave trim.

    ``origin`` is the centre of the building footprint at the wall-top bearing plane.
    ``width`` and ``depth`` are the wall footprint; overhang is added outside both. The
    pitch is measured from horizontal over half the *wall* span, so adding overhang lowers
    the outer eave without moving the ridge — the relationship a real roof keeps.
    """
    p = validate_params("add_gable_roof", op.params)
    prefix = p["object_id"]
    origin = p["origin"]
    axis = p["ridge_axis"]
    width, depth = p["width"], p["depth"]
    pitch_radians = math.radians(p["pitch_degrees"])
    pitch = math.tan(pitch_radians)
    thickness, overhang = p["thickness"], p["overhang"]
    trim_width, trim_depth = p["trim_width"], p["trim_depth"]

    # Width is always the gable span and depth is always the ridge length. Changing the
    # ridge axis rotates that architectural footprint; it does not silently swap the two
    # dimensions the caller supplied.
    span = width
    length = depth
    half_roof = span / 2.0 + overhang
    half_length = length / 2.0 + overhang
    ridge_z = origin.z + pitch * span / 2.0
    eave_z = origin.z - pitch * overhang

    neg_id = engine.create_mesh(
        f"{prefix}_slope_neg",
        *_panel_mesh(origin, axis, -half_roof, 0.0, half_length, ridge_z, pitch, thickness),
    )
    pos_id = engine.create_mesh(
        f"{prefix}_slope_pos",
        *_panel_mesh(origin, axis, 0.0, half_roof, half_length, ridge_z, pitch, thickness),
    )

    # Finish the ridge cap at the same visible height as the rake's vertical miter. The
    # previous cap merely touched the miter at its bottom corner and projected 183 mm
    # above it, which rendered as a square block perched on the white V. Lowering it by
    # the derived overlap makes the three boards read as one continuous trim system.
    rake_miter_depth = trim_depth / (2.0 * math.cos(pitch_radians))
    ridge_center_z = (
        ridge_z + thickness / 2.0 + rake_miter_depth - trim_depth / 2.0
    )
    ridge_a = _point(origin, axis, 0.0, -half_length, ridge_center_z)
    ridge_b = _point(origin, axis, 0.0, half_length, ridge_center_z)
    ridge_id = engine.create_mesh(
        f"{prefix}_ridge_cap", *oriented_box_between(ridge_a, ridge_b, trim_width, trim_depth)
    )

    trim_meshes = perimeter_trim_meshes(
        origin,
        axis,
        half_roof,
        half_length,
        eave_z + thickness / 2.0,
        ridge_z + thickness / 2.0,
        trim_width,
        trim_depth,
    )
    gable_ids = [
        engine.create_mesh(f"{prefix}_gable_{label}_trim", *trim_meshes[f"gable_{label}"])
        for label in ("neg", "pos")
    ]
    eave_ids = [
        engine.create_mesh(f"{prefix}_eave_{label}_fascia", *trim_meshes[f"eave_{label}"])
        for label in ("neg", "pos")
    ]

    return OperationResult(
        op_id=op.op_id,
        ok=True,
        produced_objects=(neg_id, pos_id, ridge_id, *gable_ids, *eave_ids),
    )


def _point(origin: Vec3, axis: str, cross: float, along: float, z: float) -> Vec3:
    if axis == "y":
        return Vec3(origin.x + cross, origin.y + along, z)
    return Vec3(origin.x + along, origin.y + cross, z)




def _panel_mesh(
    origin: Vec3,
    axis: str,
    cross_min: float,
    cross_max: float,
    half_length: float,
    ridge_z: float,
    pitch: float,
    thickness: float,
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """One closed sloped slab, vertically thickened so the two ridge faces coincide."""
    if axis == "y":
        projected = (
            (cross_min, -half_length),
            (cross_max, -half_length),
            (cross_max, half_length),
            (cross_min, half_length),
        )
    else:
        projected = (
            (cross_min, -half_length),
            (cross_min, half_length),
            (cross_max, half_length),
            (cross_max, -half_length),
        )
    bottom = [
        _point(origin, axis, cross, along, ridge_z - abs(cross) * pitch)
        for cross, along in projected
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
