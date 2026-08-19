"""``add_profiled_solid`` — exact solid extrusion and variable-section lofting.

Profiles live in a local right-handed plane and stations advance along one world axis. The
operation keeps the model's job two-dimensional while producing one closed manifold mesh.
"""

from __future__ import annotations

import math
from typing import Any

from contracts import EPSILON, EngineProtocol, Operation, OperationResult, ToolError, Vec3

from .validation import validate_params

__all__ = ["add_profiled_solid"]


Point2 = tuple[float, float]
Section = tuple[float, tuple[Point2, ...]]


def _error(rule: str, detail: str, suggestion: str) -> ToolError:
    return ToolError(rule, f"add_profiled_solid: {detail}", suggestion)


def _point(value: Any, section_index: int, point_index: int) -> Point2:
    try:
        u, v = value
        point = (float(u), float(v))
    except (TypeError, ValueError):
        raise _error(
            "ops.profiled_bad_point",
            f"section {section_index} point {point_index} is {value!r}, not [u, v]",
            "pass every profile point as two finite numbers in metres",
        ) from None
    if not all(math.isfinite(component) for component in point):
        raise _error(
            "ops.profiled_bad_point",
            f"section {section_index} point {point_index} contains a non-finite number",
            "replace NaN or infinity with a finite local coordinate",
        )
    return point


def _signed_area(profile: tuple[Point2, ...]) -> float:
    return 0.5 * sum(
        u0 * v1 - u1 * v0
        for (u0, v0), (u1, v1) in zip(profile, profile[1:] + profile[:1])
    )


def _is_convex_ccw(profile: tuple[Point2, ...]) -> bool:
    signs = []
    for index in range(len(profile)):
        a = profile[index - 1]
        b = profile[index]
        c = profile[(index + 1) % len(profile)]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        signs.append(cross)
    return all(value > EPSILON * EPSILON for value in signs)


def _sections(raw: Any, bevel_width: float) -> tuple[Section, ...]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        count = len(raw) if isinstance(raw, (list, tuple)) else 0
        raise _error(
            "ops.profiled_station_count", f"received {count} station(s), needs at least 2",
            "pass at least a start and end section",
        )

    sections: list[Section] = []
    expected_points: int | None = None
    previous_offset: float | None = None
    smallest_feature = math.inf
    for section_index, item in enumerate(raw):
        if not isinstance(item, dict) or "offset" not in item or "profile" not in item:
            raise _error(
                "ops.profiled_bad_section",
                f"section {section_index} must contain offset and profile",
                "pass {'offset': metres, 'profile': [[u, v], ...]}",
            )
        try:
            offset = float(item["offset"])
        except (TypeError, ValueError):
            raise _error(
                "ops.profiled_bad_section",
                f"section {section_index} offset is {item['offset']!r}",
                "pass a finite offset in metres",
            ) from None
        if not math.isfinite(offset):
            raise _error(
                "ops.profiled_bad_section", f"section {section_index} offset is not finite",
                "pass a finite offset in metres",
            )
        if previous_offset is not None:
            gap = offset - previous_offset
            if gap <= EPSILON:
                raise _error(
                    "ops.profiled_station_order",
                    f"section {section_index} offset {offset} does not follow {previous_offset}",
                    "supply strictly increasing offsets; the tool does not reorder stations",
                )
            smallest_feature = min(smallest_feature, gap)
        previous_offset = offset

        raw_profile = item["profile"]
        if not isinstance(raw_profile, (list, tuple)) or len(raw_profile) < 3:
            raise _error(
                "ops.profiled_correspondence",
                f"section {section_index} has fewer than 3 profile points",
                "pass a closed polygon as at least three ordered points",
            )
        profile = tuple(
            _point(value, section_index, point_index)
            for point_index, value in enumerate(raw_profile)
        )
        if expected_points is None:
            expected_points = len(profile)
        elif len(profile) != expected_points:
            raise _error(
                "ops.profiled_correspondence",
                f"section {section_index} has {len(profile)} points; expected {expected_points}",
                "use the same vertex count and corresponding order at every station",
            )
        for point_index, point in enumerate(profile):
            for earlier_index, earlier in enumerate(profile[:point_index]):
                distance = math.hypot(point[0] - earlier[0], point[1] - earlier[1])
                if distance <= EPSILON:
                    raise _error(
                        "ops.profiled_duplicate_point",
                        f"section {section_index} point {point_index} duplicates point {earlier_index}",
                        "remove repeated profile points",
                    )
            nxt = profile[(point_index + 1) % len(profile)]
            smallest_feature = min(
                smallest_feature, math.hypot(nxt[0] - point[0], nxt[1] - point[1])
            )
        if _signed_area(profile) <= EPSILON * EPSILON:
            raise _error(
                "ops.profiled_winding",
                f"section {section_index} is clockwise or has zero area",
                "list profile points counter-clockwise in the local [u, v] plane",
            )
        if not _is_convex_ccw(profile):
            raise _error(
                "ops.profiled_non_convex", f"section {section_index} is not strictly convex",
                "use a convex profile without collinear or inward-turning corners",
            )
        sections.append((offset, profile))

    if bevel_width > 0 and 2.0 * bevel_width >= smallest_feature - EPSILON:
        raise _error(
            "ops.profiled_bevel_does_not_fit",
            f"bevel_width {bevel_width} consumes the smallest {smallest_feature:.4g} m feature",
            f"use bevel_width below {smallest_feature / 2.0:.4g} m",
        )
    return tuple(sections)


def _world_point(origin: Vec3, axis: str, offset: float, u: float, v: float) -> Vec3:
    if axis == "x":
        return Vec3(origin.x + offset, origin.y + u, origin.z + v)
    if axis == "y":
        # Local u points toward world -X so u x v equals the +Y loft axis.
        return Vec3(origin.x - u, origin.y + offset, origin.z + v)
    return Vec3(origin.x + u, origin.y + v, origin.z + offset)


def _mesh(origin: Vec3, axis: str, sections: tuple[Section, ...]):
    point_count = len(sections[0][1])
    vertices = [
        _world_point(origin, axis, offset, u, v)
        for offset, profile in sections
        for u, v in profile
    ]
    faces: list[tuple[int, ...]] = [tuple(range(point_count - 1, -1, -1))]
    for station_index in range(len(sections) - 1):
        first = station_index * point_count
        second = (station_index + 1) * point_count
        for point_index in range(point_count):
            nxt = (point_index + 1) % point_count
            faces.append((first + point_index, first + nxt, second + nxt, second + point_index))
    last = (len(sections) - 1) * point_count
    faces.append(tuple(last + index for index in range(point_count)))
    return vertices, faces


def add_profiled_solid(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build one closed solid from corresponding convex sections."""
    p = validate_params("add_profiled_solid", op.params)
    sections = _sections(p["sections"], p["bevel_width"])
    vertices, faces = _mesh(p["origin"], p["axis"], sections)
    object_id = engine.create_mesh(p["object_id"], vertices, faces)
    if p["bevel_width"] > 0:
        engine.bevel_edges(object_id, width=p["bevel_width"], segments=2)
    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(object_id,))
