"""Semantic roof-window and wall-sign operations."""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult, ToolError, Transform, Vec3

from ._geom import box_mesh
from .surface_frame import SurfaceFrame, roof_frame, wall_frame
from .validation import validate_params

__all__ = ["add_roof_window", "add_wall_sign"]


def _box(frame: SurfaceFrame, centre: Vec3, width: float, height: float, depth: float):
    offsets = [
        frame.horizontal * x + frame.vertical * y + frame.normal * z
        for z in (-depth / 2, depth / 2)
        for y in (-height / 2, height / 2)
        for x in (-width / 2, width / 2)
    ]
    # Reorder the cartesian-product vertices to the conventional box winding.
    order = (0, 1, 3, 2, 4, 5, 7, 6)
    verts = [centre + offsets[i] for i in order]
    return verts, box_mesh(Vec3(-1, -1, -1), Vec3(1, 1, 1))[1]


def _fit_error(kind: str, detail: str) -> ToolError:
    return ToolError("ops.surface_detail_does_not_fit", f"{kind}: {detail} does not fit on its host surface", "reduce the detail dimensions or edge margin")


def add_roof_window(engine: EngineProtocol, op: Operation) -> OperationResult:
    p = validate_params("add_roof_window", op.params)
    frame = roof_frame(engine, p["roof_id"])
    width, height = p["width"], p["height"]
    border, depth = p["frame_width"], p["depth"]
    if width > frame.width or height > frame.height or border * 2 >= min(width, height):
        raise _fit_error("add_roof_window", f"{width:.3f}m x {height:.3f}m window")
    hf, vf = p["horizontal_fraction"], p["vertical_fraction"]
    h = frame.horizontal_min + width / 2 + hf * (frame.width - width)
    v = frame.vertical_min + height / 2 + vf * (frame.height - height)
    surface = frame.point(h, v)

    glass_id = engine.create_mesh(
        f"{p['object_id']}_glass",
        *_box(frame, surface + frame.normal * (depth * 0.25), width - 2 * border, height - 2 * border, depth * 0.5),
    )
    parts = []
    for suffix, cw, ch, dh, dv in (
        ("", border, height, -(width - border) / 2, 0),
        ("right", border, height, (width - border) / 2, 0),
        ("bottom", width - 2 * border, border, 0, -(height - border) / 2),
        ("top", width - 2 * border, border, 0, (height - border) / 2),
    ):
        centre = surface + frame.horizontal * dh + frame.vertical * dv + frame.normal * (depth / 2)
        part_id = f"{p['object_id']}_frame" + (f"_{suffix}" if suffix else "")
        parts.append(engine.create_mesh(part_id, *_box(frame, centre, cw, ch, depth)))
    frame_id = engine.join(parts[0], parts[1:])
    return OperationResult(op.op_id, True, produced_objects=(glass_id, frame_id))


def add_wall_sign(engine: EngineProtocol, op: Operation) -> OperationResult:
    p = validate_params("add_wall_sign", op.params)
    frame = wall_frame(engine, p["wall_id"], p["toward"])
    h = (frame.horizontal_min + frame.horizontal_max) / 2
    v = p["center_height"]
    margin = p["edge_margin"]
    if v - p["height"] / 2 < frame.vertical_min + margin or v + p["height"] / 2 > frame.vertical_max - margin:
        raise _fit_error("add_wall_sign", f"text at height {v:.3f}m")
    centre = frame.point(h, v, p["depth"] / 2)
    created = engine.create_text(
        p["object_id"], p["text"], p["height"], p["depth"],
        Transform(translation=centre, rotation=frame.rotation()),
    )
    vertices = engine.snapshot(created).world_vertices()
    hs = [point.dot(frame.horizontal) for point in vertices]
    vs = [point.dot(frame.vertical) for point in vertices]
    if min(hs) < frame.horizontal_min + margin or max(hs) > frame.horizontal_max - margin or min(vs) < frame.vertical_min + margin or max(vs) > frame.vertical_max - margin:
        engine.delete(created)
        raise _fit_error("add_wall_sign", f"text {p['text']!r}")
    return OperationResult(op.op_id, True, produced_objects=(created,))
