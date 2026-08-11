"""``add_gable_roof`` — a detailed roof assembly derived from architectural dimensions."""

from __future__ import annotations

import math

from contracts import EngineProtocol, Operation, OperationResult, Vec3

from ._geom import oriented_box_between
from .validation import validate_params

__all__ = ["add_gable_roof"]


def add_gable_roof(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build two exact-pitch slabs plus ridge, rake trim and eave fascia.

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
    pitch = math.tan(math.radians(p["pitch_degrees"]))
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

    ridge_a = _point(origin, axis, 0.0, -half_length, ridge_z + thickness + trim_depth / 2.0)
    ridge_b = _point(origin, axis, 0.0, half_length, ridge_z + thickness + trim_depth / 2.0)
    ridge_id = engine.create_mesh(
        f"{prefix}_ridge_cap", *oriented_box_between(ridge_a, ridge_b, trim_width, trim_depth)
    )

    gable_ids = []
    for along_sign, label in ((-1.0, "neg"), (1.0, "pos")):
        along = along_sign * (half_length + trim_width / 2.0)
        points = (
            _point(origin, axis, -half_roof, along, eave_z + thickness / 2.0),
            _point(origin, axis, 0.0, along, ridge_z + thickness / 2.0),
            _point(origin, axis, half_roof, along, eave_z + thickness / 2.0),
        )
        left_end = points[1] - (points[1] - points[0]).normalized() * (trim_depth / 2.0)
        right_start = points[1] + (points[2] - points[1]).normalized() * (trim_depth / 2.0)
        trim_id = engine.create_mesh(
            f"{prefix}_gable_{label}_trim",
            *oriented_box_between(points[0], left_end, trim_width, trim_depth),
        )
        extra_id = engine.create_mesh(
            f"{prefix}_gable_{label}_trim_part",
            *oriented_box_between(right_start, points[2], trim_width, trim_depth),
        )
        engine.join(trim_id, [extra_id])
        gable_ids.append(trim_id)

    eave_ids = []
    for cross_sign, label in ((-1.0, "neg"), (1.0, "pos")):
        cross = cross_sign * (half_roof + trim_width / 2.0)
        a = _point(origin, axis, cross, -half_length, eave_z + thickness / 2.0)
        b = _point(origin, axis, cross, half_length, eave_z + thickness / 2.0)
        eave_ids.append(
            engine.create_mesh(
                f"{prefix}_eave_{label}_fascia",
                *oriented_box_between(a, b, trim_width, trim_depth),
            )
        )

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
