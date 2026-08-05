"""``AlignResult`` — what every ``align`` entry point returns."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AlignResult"]


@dataclass(frozen=True, slots=True)
class AlignResult:
    """The outcome of one immediate-snap alignment.

    ``changed=False`` means the object was already aligned to within tolerance and
    ``engine.set_transform`` was never called — not called-with-the-same-value, *never
    called* — so the object's stored transform stays bit-for-bit what it was (the
    "already-aligned objects do not move at all" invariant every ``align`` test checks
    for).

    ``angle_before_deg``/``angle_after_deg`` are always the metric the specific operation
    is actually about: the two-object dominant-axis angle (``measure.angle_between``) for
    ``make_parallel``/``make_perpendicular``/``set_angle``/``make_flush``; the object's own
    up-vs-world-up angle for ``make_plumb``; its own normal-vs-target-plane angle for
    ``make_coplanar``; its own yaw for ``snap_to_grid``. Both fields are always populated
    (never ``None``) so a caller never has to branch on which operation produced a given
    result before reading them.
    """

    object_id: str
    changed: bool
    angle_before_deg: float
    angle_after_deg: float
    detail: str
