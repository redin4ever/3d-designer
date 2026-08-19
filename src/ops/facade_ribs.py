"""Opening-aware façade rib layout derived from the wall's remaining face."""

from __future__ import annotations

import math

from contracts import EngineProtocol, Operation, OperationResult, ToolError

from .surface_frame import wall_frame
from .surface_mounts import _box
from .validation import validate_params

__all__ = ["add_facade_ribs"]


def _intervals_at(regions, horizontal: float) -> list[tuple[float, float]]:
    spans = []
    for triangle in regions:
        hits = []
        for a, b in zip(triangle, (*triangle[1:], triangle[0])):
            x0, z0 = a
            x1, z1 = b
            if horizontal < min(x0, x1) - 1e-7 or horizontal > max(x0, x1) + 1e-7:
                continue
            if abs(x1 - x0) < 1e-9:
                if abs(horizontal - x0) < 1e-7:
                    hits.extend((z0, z1))
            else:
                t = (horizontal - x0) / (x1 - x0)
                hits.append(z0 + t * (z1 - z0))
        if len(hits) >= 2:
            spans.append((min(hits), max(hits)))
    spans.sort()
    merged: list[list[float]] = []
    for low, high in spans:
        if high - low < 1e-7:
            continue
        if merged and low <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]


def _intersection(a: list[tuple[float, float]], b: list[tuple[float, float]]):
    return [
        (max(a0, b0), min(a1, b1))
        for a0, a1 in a for b0, b1 in b
        if max(a0, b0) < min(a1, b1) - 1e-7
    ]


def add_facade_ribs(engine: EngineProtocol, op: Operation) -> OperationResult:
    p = validate_params("add_facade_ribs", op.params)
    frame = wall_frame(engine, p["wall_id"], p["toward"])
    spacing, width = p["spacing"], p["width"]
    first = math.ceil((frame.horizontal_min + p["edge_margin"]) / spacing) * spacing
    last = frame.horizontal_max - p["edge_margin"]
    planned = []
    horizontal = first
    while horizontal <= last + 1e-7:
        spans = _intervals_at(frame.regions, horizontal)
        spans = _intersection(spans, _intervals_at(frame.regions, horizontal - width / 2))
        spans = _intersection(spans, _intervals_at(frame.regions, horizontal + width / 2))
        for low, high in spans:
            low += p["opening_clearance"]
            high -= p["opening_clearance"]
            if high - low >= p["min_segment"]:
                planned.append((horizontal, low, high))
        horizontal += spacing
    if not planned:
        raise ToolError(
            "ops.no_facade_rib_segments",
            f"add_facade_ribs: no segment of {p['wall_id']!r} satisfies the requested clearances",
            "reduce edge_margin, opening_clearance, min_segment, or spacing",
        )

    created = []
    for index, (horizontal, low, high) in enumerate(planned):
        centre = frame.point(horizontal, (low + high) / 2, p["depth"] / 2)
        part_id = p["object_id"] if index == 0 else f"{p['object_id']}_segment_{index:03d}"
        created.append(engine.create_mesh(
            part_id,
            *_box(frame, centre, width, high - low, p["depth"]),
        ))
    result = engine.join(created[0], created[1:])
    return OperationResult(op.op_id, True, produced_objects=(result,))
