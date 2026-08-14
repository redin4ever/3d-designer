"""The seven metric queries. See ``src/measure/README.md`` for the full contract.

Every function here is a number the tool computes and hands to the agent as fact,
replacing a guess: vision models land within 2x of ground truth on visual distance
estimation about 37% of the time (``contracts.measurement.MetricKind``).

Pure: none of these call a mutating ``EngineProtocol`` method (``set_transform``,
``apply_transform``, ``join``, any ``ModifierOps`` method, …). Only ``snapshot``,
``world_bounds``, ``list_objects`` and ``exists``.
"""

from __future__ import annotations

import math

from contracts import EngineProtocol, Measurement, MetricKind

from ._distance import mesh_distance
from ._geom import aabb_gap_vector, dominant_local_axis, signed_tetra_volume

__all__ = [
    "bounds",
    "dimensions",
    "distance",
    "angle_between",
    "surface_angle",
    "gap_width",
    "volume",
    "triangle_count",
]


def bounds(engine: EngineProtocol, object_id: str) -> Measurement:
    """World-space axis-aligned bounding box of one object. ``MetricKind.BOUNDS``.

    ``value`` is the box's world-space minimum corner — position-sensitive, unlike a
    local-space or hardcoded reading, so two identical objects at different
    translations report different values (see ``metrics_test.py::
    test_bounds_value_differs_between_objects_at_different_positions``). The maximum
    corner rides along in ``detail`` so no information is lost to the 3-float value
    shape ``Measurement`` uses for every metric.
    """
    aabb = engine.world_bounds(object_id)
    mx, my, mz = aabb.maximum.as_tuple()
    return Measurement(
        kind=MetricKind.BOUNDS,
        value=aabb.minimum.as_tuple(),
        unit="m",
        subject=object_id,
        detail=f"max=({mx:.6g}, {my:.6g}, {mz:.6g})",
    )


def dimensions(engine: EngineProtocol, object_id: str) -> Measurement:
    """``(x, y, z)`` world-space extents in metres. ``MetricKind.DIMENSIONS``."""
    size = engine.world_bounds(object_id).size
    return Measurement(kind=MetricKind.DIMENSIONS, value=size.as_tuple(), unit="m", subject=object_id)


def distance(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Closest surface-to-surface distance between two objects, in metres.

    Never negative: 0 when the objects touch or overlap, never a signed penetration depth —
    that is what :func:`measure.find_clipping` is for. ``MetricKind.DISTANCE``.

    Measured against the real triangles, not the bounding boxes. An AABB is exact for an
    axis-aligned box and badly wrong for anything rotated: two 4 m beams yawed 45° and
    1.4 m apart reported 0.0 because their boxes overlap. ADR-005 gives this number
    authority over the agent's own judgement, so a confidently wrong one is worse than
    none — the agent moves correct geometry to close a gap that is not there.
    """
    value, exact = mesh_distance(engine.snapshot(a), engine.snapshot(b))
    return Measurement(
        kind=MetricKind.DISTANCE, value=value, unit="m", subject=f"{a}|{b}",
        detail="" if exact else "bounding-box lower bound: too many triangles to sweep exactly",
    )


def angle_between(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Angle in degrees between the two objects' dominant axes. ``MetricKind.ANGLE``.

    Each object's "dominant axis" is the local axis spanning its largest extent (the
    long axis of a post, say), rotated into world space by its own transform. A
    railing-post generator that tips a post at the wrong angle produces no visual
    tell in a render; this is the number that catches it instead.
    """
    snap_a = engine.snapshot(a)
    snap_b = engine.snapshot(b)
    axis_a = snap_a.transform.rotation.rotate(dominant_local_axis(snap_a.vertices)).normalized()
    axis_b = snap_b.transform.rotation.rotate(dominant_local_axis(snap_b.vertices)).normalized()
    cosine = max(-1.0, min(1.0, axis_a.dot(axis_b)))
    degrees = math.degrees(math.acos(cosine))
    return Measurement(kind=MetricKind.ANGLE, value=degrees, unit="deg", subject=f"{a}|{b}")


def surface_angle(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Acute angle between the dominant planar surfaces of two objects."""
    raise NotImplementedError("measure.surface_angle: not implemented")


def gap_width(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Shortest empty span between two objects.

    0 when they touch or overlap — this is the number a "close every gap under 5mm" task is
    defined against (ADR-005). ``MetricKind.GAP_WIDTH``.

    Measured against the real triangles, for the same reason :func:`distance` is: a
    bounding box overstates any rotated object, and a gap reported as 0 means no
    gap-closing work is ever triggered for a joint that is visibly open.
    """
    value, exact = mesh_distance(engine.snapshot(a), engine.snapshot(b))
    return Measurement(
        kind=MetricKind.GAP_WIDTH, value=value, unit="m", subject=f"{a}|{b}",
        detail="" if exact else "bounding-box lower bound: too many triangles to sweep exactly",
    )


def volume(engine: EngineProtocol, object_id: str) -> Measurement:
    """Enclosed volume in cubic metres. ``MetricKind.VOLUME``.

    The signed-tetrahedron sum over every world-space triangle (divergence theorem),
    never the bounding box's extents multiplied together — those agree only for an
    axis-aligned box and diverge sharply for anything else (see ``metrics_test.py::
    test_volume_of_a_pyramid_is_not_its_bounding_box``).
    """
    snap = engine.snapshot(object_id)
    verts = snap.world_vertices()
    total = sum(signed_tetra_volume(verts[i], verts[j], verts[k]) for i, j, k in snap.triangles)
    return Measurement(kind=MetricKind.VOLUME, value=abs(total), unit="m^3", subject=object_id)


def triangle_count(engine: EngineProtocol, object_id: str) -> Measurement:
    """Triangle count of the object's evaluated mesh. ``MetricKind.TRIANGLE_COUNT``."""
    snap = engine.snapshot(object_id)
    return Measurement(
        kind=MetricKind.TRIANGLE_COUNT, value=len(snap.triangles), unit="", subject=object_id
    )
