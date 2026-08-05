"""Tests for the seven metric queries.

Every metric here replaces a guess an agent would otherwise make from a render: vision
models land within 2x of ground truth on visual distance estimation about 37% of the time
(``contracts.measurement.MetricKind``). If any of these lies, every downstream decision
built on it — spacing, proportion, "is this railing 0.95m tall" — is built on the same lie.
"""

from __future__ import annotations

import math

import pytest

from contracts import MetricKind, Quat, Transform, Vec3
from measure import (
    angle_between,
    bounds,
    dimensions,
    distance,
    gap_width,
    triangle_count,
    volume,
)


def test_dimensions_of_a_box(engine) -> None:
    """A generator that asks "make this 2x4x1" and gets a wrong dimensions reading back has
    no way to tell it worked; this is the number that closes that loop."""
    engine.create_primitive("box", "cube", Vec3(2.0, 4.0, 1.0))

    m = dimensions(engine, "box")

    assert m.kind is MetricKind.DIMENSIONS
    assert m.value == pytest.approx((2.0, 4.0, 1.0))
    assert m.unit == "m"
    assert m.subject == "box"


def test_bounds_reports_the_right_metric_kind_and_subject(engine) -> None:
    """The world-space AABB feeds every broad-phase clipping and gap query; a report tagged
    with the wrong kind or subject would be silently misrouted by any caller that dispatches
    on those fields."""
    engine.create_primitive("box", "cube", Vec3(2.0, 4.0, 1.0), Transform(translation=Vec3(1, 0, 0)))

    m = bounds(engine, "box")

    assert m.kind is MetricKind.BOUNDS
    assert m.subject == "box"


def test_distance_between_separated_boxes(engine) -> None:
    """This is the number that replaces a human eyeballing "0.5m apart" from a render —
    get it wrong and every spacing decision downstream is built on a guess."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(1.5, 0, 0)))

    m = distance(engine, "a", "b")

    assert m.kind is MetricKind.DISTANCE
    assert m.subject == "a|b"
    assert m.value == pytest.approx(0.5, abs=1e-6)


def test_distance_between_touching_boxes_is_zero(engine) -> None:
    """A "these parts touch" state must read as exactly 0, not a small positive number an
    agent could misread as a gap it should try to close."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(1.0, 0, 0)))

    m = distance(engine, "a", "b")

    assert m.value == pytest.approx(0.0, abs=1e-6)


def test_distance_between_overlapping_boxes_is_zero_not_negative(engine) -> None:
    """A negative distance would read as "even closer than touching" — nonsense an agent
    could still act on if the sign is not clamped away before it reaches the report."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(0.5, 0, 0)))

    m = distance(engine, "a", "b")

    assert m.value >= 0.0
    assert m.value == pytest.approx(0.0, abs=1e-6)


def test_gap_width_of_overlapping_parts_is_zero(engine) -> None:
    """Same non-negativity requirement as distance, for the metric a "close every gap under
    5mm" task is defined against (ADR-005)."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(0.5, 0, 0)))

    m = gap_width(engine, "a", "b")

    assert m.kind is MetricKind.GAP_WIDTH
    assert m.value == pytest.approx(0.0, abs=1e-6)
    assert m.value >= 0.0


def test_triangle_count_matches_the_snapshot(engine) -> None:
    """A wrong triangle count corrupts every polygon-budget check downstream (Gate A 12.2)
    — the export banner would understate or overstate the exact thing it exists to warn
    about."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    expected = engine.snapshot("box").triangle_count

    m = triangle_count(engine, "box")

    assert m.kind is MetricKind.TRIANGLE_COUNT
    assert m.value == expected


def test_volume_of_a_unit_cube_is_one(engine) -> None:
    """A wrong volume corrupts any downstream material/cost/physics estimate built on it —
    there is no render-based way to catch a volume that is subtly wrong."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    m = volume(engine, "box")

    assert m.kind is MetricKind.VOLUME
    assert m.value == pytest.approx(1.0, rel=1e-3)


def test_angle_between_identical_upright_posts_is_zero(engine) -> None:
    """The zero case has to genuinely be zero, or the 90-degree case below proves nothing
    about the metric being sensitive to angle rather than returning noise."""
    engine.create_primitive("post_a", "cube", Vec3(0.1, 0.1, 1.0))
    engine.create_primitive(
        "post_b", "cube", Vec3(0.1, 0.1, 1.0), Transform(translation=Vec3(2, 0, 0))
    )

    m = angle_between(engine, "post_a", "post_b")

    assert m.kind is MetricKind.ANGLE
    assert m.value == pytest.approx(0.0, abs=1e-2)


def test_angle_between_perpendicular_posts_is_ninety_degrees(engine) -> None:
    """A railing-post generator that gets this wrong produces posts leaning at the wrong
    angle with no visual tell — the exact naive-generator error this query exists to catch
    without needing a render."""
    engine.create_primitive("post_a", "cube", Vec3(0.1, 0.1, 1.0))
    tipped = Transform(rotation=Quat.from_axis_angle(Vec3(0, 1, 0), math.pi / 2))
    engine.create_primitive("post_b", "cube", Vec3(0.1, 0.1, 1.0), tipped)

    m = angle_between(engine, "post_a", "post_b")

    assert m.value == pytest.approx(90.0, abs=1e-1)
