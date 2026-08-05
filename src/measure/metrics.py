"""Stub — the seven metric queries. See ``src/measure/README.md`` for the full contract.

Every function here is a number the tool computes and hands to the agent as fact, replacing
a guess: vision models land within 2x of ground truth on visual distance estimation about
37% of the time (``contracts.measurement.MetricKind``). Nothing below computes anything yet
— every function raises until an implementer replaces the body.

Pure: none of these may call a mutating ``EngineProtocol`` method (``set_transform``,
``apply_transform``, ``join``, any ``ModifierOps`` method, …). Only ``snapshot``,
``world_bounds``, ``list_objects`` and ``exists``.
"""

from __future__ import annotations

from contracts import EngineProtocol, Measurement

__all__ = [
    "bounds",
    "dimensions",
    "distance",
    "angle_between",
    "gap_width",
    "volume",
    "triangle_count",
]


def bounds(engine: EngineProtocol, object_id: str) -> Measurement:
    """World-space axis-aligned bounding box of one object. ``MetricKind.BOUNDS``."""
    raise NotImplementedError("measure.bounds: not implemented")


def dimensions(engine: EngineProtocol, object_id: str) -> Measurement:
    """``(x, y, z)`` world-space extents in metres. ``MetricKind.DIMENSIONS``."""
    raise NotImplementedError("measure.dimensions: not implemented")


def distance(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Closest surface-to-surface distance between two objects.

    Never negative: 0 when the objects touch or overlap, never a signed penetration depth
    — that is what :func:`measure.find_clipping` is for. ``MetricKind.DISTANCE``.
    """
    raise NotImplementedError("measure.distance: not implemented")


def angle_between(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Angle in degrees between the two objects' dominant axes. ``MetricKind.ANGLE``."""
    raise NotImplementedError("measure.angle_between: not implemented")


def gap_width(engine: EngineProtocol, a: str, b: str) -> Measurement:
    """Shortest empty span between two objects.

    0 when they touch or overlap — this is the number a "close every gap under 5mm" task
    is defined against (ADR-005). ``MetricKind.GAP_WIDTH``.
    """
    raise NotImplementedError("measure.gap_width: not implemented")


def volume(engine: EngineProtocol, object_id: str) -> Measurement:
    """Enclosed volume in cubic metres. ``MetricKind.VOLUME``."""
    raise NotImplementedError("measure.volume: not implemented")


def triangle_count(engine: EngineProtocol, object_id: str) -> Measurement:
    """Triangle count of the object's evaluated mesh. ``MetricKind.TRIANGLE_COUNT``."""
    raise NotImplementedError("measure.triangle_count: not implemented")
