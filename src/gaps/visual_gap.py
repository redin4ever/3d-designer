"""``close_visual_gap`` — bring two touching-but-not-touching parts together.

``DefectClass.VISUAL_GAP``: passes every manifold check because each part is individually
fine, and is invisible to a render-based review at anything but point-blank range. No
``EngineProtocol`` primitive moves an object toward another by a measured amount — this
composes ``world_bounds`` and ``set_transform``, the two primitives that exist.
"""

from __future__ import annotations

from contracts import AABB, EngineProtocol, RepairOutcome, Transform, Vec3
from measure import gap_width

__all__ = ["close_visual_gap"]


def _gap_vector(a: AABB, b: AABB) -> Vec3:
    """The per-axis empty span from ``a`` to ``b`` — 0 on any axis where they already
    touch or overlap. Adding this to ``a``'s translation makes the two boxes touch on
    every axis at once; ``measure.gap_width`` is what confirms it actually did."""

    def axis_gap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
        if a_hi < b_lo:
            return b_lo - a_hi
        if b_hi < a_lo:
            return b_hi - a_lo
        return 0.0

    return Vec3(
        axis_gap(a.minimum.x, a.maximum.x, b.minimum.x, b.maximum.x),
        axis_gap(a.minimum.y, a.maximum.y, b.minimum.y, b.maximum.y),
        axis_gap(a.minimum.z, a.maximum.z, b.minimum.z, b.maximum.z),
    )


def close_visual_gap(engine: EngineProtocol, a: str, b: str, *, max_gap: float) -> RepairOutcome:
    """Translate ``a`` toward ``b`` by the measured gap, so they touch.

    Skips (never silently no-ops as "fixed") when the gap exceeds ``max_gap`` — the same
    "found work and declined it" distinction ``fill_boundary_holes(max_sides=...)`` makes,
    for the same reason (``contracts.RepairOutcome``).
    """
    gap = gap_width(engine, a, b).value
    if gap <= 0.0:
        return RepairOutcome()  # already touching or overlapping — nothing to do
    if gap > max_gap:
        return RepairOutcome(
            fixed=0, skipped=1, reason=f"gap {gap:.4g}m exceeds max_gap {max_gap:.4g}m",
        )

    vector = _gap_vector(engine.world_bounds(a), engine.world_bounds(b))
    t = engine.snapshot(a).transform
    engine.set_transform(
        a, Transform(translation=t.translation + vector, rotation=t.rotation, scale=t.scale)
    )

    after = gap_width(engine, a, b).value
    if after > 1e-9:
        return RepairOutcome(fixed=0, skipped=1, reason=f"residual gap {after:.4g}m remains")
    return RepairOutcome(fixed=1)
