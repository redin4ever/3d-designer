"""Pure geometry helpers for ``array_along_curve`` — no bpy, no contracts.geometry logic
beyond ``Vec3``/``Quat`` themselves.

Deliberately independent of ``testing.mesh_helpers`` (which implements the same generic
curve math for ``FakeEngine``): this is ordinary polyline geometry, not a `FakeEngine`
internal, and production code in ``src/engine/`` must not depend on ``src/testing/`` (test
infrastructure is not a runtime dependency — see ``src/engine/CLAUDE.md``'s boundary rules).
"""

from __future__ import annotations

import math
from typing import Sequence

from contracts import EngineError, Quat, Vec3, WORLD_UP

__all__ = ["sample_polyline", "arc_length_to", "tangent_at", "rotation_from_up_to"]


def sample_polyline(points: Sequence[Vec3], spacing: float) -> list[Vec3]:
    """Positions at a regular arc-length interval along a polyline, endpoints always included.

    The ``spacing`` guard is not defensive decoration. ``t += spacing`` with ``spacing == 0``
    never advances and the loop below never ends — a direct call hangs the process and grows
    ``out`` until memory runs out, rather than returning something wrong a caller could
    notice (F-025). ``array_along_curve`` happens to validate first, so nothing in the
    product reaches this today; the twin in ``testing/mesh_helpers.py`` has guarded it since
    it was written, and this copy having drifted is exactly the risk the duplication carries.

    It raises the same ``engine.bad_spacing`` rule ``array_along_curve`` raises, so a direct
    caller and a caller going through the mixin get an identical, actionable failure. (The
    twin raises a bare ``ValueError``; matching *that* would mean an unnamed error escaping
    ``src/engine/``, which this module's convention forbids — see ``CLAUDE.md``.)
    """
    if spacing <= 0:
        raise EngineError(
            "engine.bad_spacing",
            f"spacing {spacing} must be positive",
            "pass a spacing greater than zero — it is the arc length between samples, "
            "so zero or less has no number of positions that satisfies it",
        )
    out = [points[0]]
    carry = 0.0
    for a, b in zip(points, points[1:]):
        seg = b - a
        length = seg.length()
        if length < 1e-9:
            continue
        direction = seg * (1.0 / length)
        t = spacing - carry
        while t <= length + 1e-9:
            out.append(a + direction * t)
            t += spacing
        carry = (carry + length) % spacing
    if (out[-1] - points[-1]).length() > 1e-6:
        out.append(points[-1])
    return out


def arc_length_to(points: Sequence[Vec3], target: Vec3) -> float:
    """Distance along the polyline to the point nearest ``target`` — used to order instances
    when forced positions (corners) are mixed in with regularly spaced ones."""
    total = 0.0
    best = math.inf
    best_len = 0.0
    for a, b in zip(points, points[1:]):
        seg = b - a
        length = seg.length()
        if length > 1e-9:
            t = max(0.0, min(1.0, (target - a).dot(seg) / (length * length)))
            d = (target - (a + seg * t)).length()
            if d < best:
                best, best_len = d, total + t * length
        total += length
    return best_len


def tangent_at(points: Sequence[Vec3], position: Vec3) -> Vec3:
    """Unit direction of the polyline segment nearest ``position``."""
    best, best_dist = points[1] - points[0], math.inf
    for a, b in zip(points, points[1:]):
        seg = b - a
        length = seg.length()
        if length < 1e-9:
            continue
        t = max(0.0, min(1.0, (position - a).dot(seg) / (length * length)))
        d = (position - (a + seg * t)).length()
        if d < best_dist:
            best, best_dist = seg, d
    return best.normalized()


def rotation_from_up_to(direction: Vec3) -> Quat:
    """The rotation taking world up onto ``direction`` — what a fence post must NOT get when
    ``keep_upright=True`` (see ``ModifierOps.array_along_curve``'s docstring)."""
    d = direction.normalized()
    axis = WORLD_UP.cross(d)
    if axis.length() < 1e-9:
        return Quat.identity() if d.z > 0 else Quat.from_axis_angle(Vec3(1, 0, 0), math.pi)
    return Quat.from_axis_angle(axis, math.acos(max(-1.0, min(1.0, WORLD_UP.dot(d)))))
