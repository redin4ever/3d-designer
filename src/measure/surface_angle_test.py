"""Regression coverage for host-surface alignment.

Long-axis angle cannot distinguish a skylight lying on a roof from one standing on its
edge. Surface angle compares the dominant faces instead and is the geometry authority for
surface-mounted operation acceptance.
"""

from __future__ import annotations

import math

import pytest

from contracts import AcceptanceQuery, Comparison, MetricKind, Quat, Transform, Vec3
from measure import MEASURE_SPECS, evaluate, surface_angle


def _plate(engine, name: str, rotation: Quat = Quat()) -> None:
    engine.create_primitive(
        name,
        "cube",
        Vec3(3.0, 2.0, 0.08),
        Transform(rotation=rotation),
    )


def test_surface_angle_catches_a_roof_window_standing_on_edge(engine) -> None:
    _plate(engine, "roof")
    _plate(engine, "window", Quat.from_axis_angle(Vec3(1, 0, 0), math.pi / 2))

    measured = surface_angle(engine, "roof", "window")

    assert measured.kind is MetricKind.SURFACE_ANGLE
    assert measured.value == pytest.approx(90.0, abs=1e-6)
    assert measured.subject == "roof|window"


def test_surface_angle_treats_opposite_parallel_normals_as_aligned(engine) -> None:
    _plate(engine, "roof")
    _plate(engine, "window", Quat.from_axis_angle(Vec3(1, 0, 0), math.pi))

    assert surface_angle(engine, "roof", "window").value == pytest.approx(0.0, abs=1e-6)


def test_surface_angle_drives_acceptance_with_a_one_degree_tolerance(engine) -> None:
    _plate(engine, "roof")
    _plate(engine, "good", Quat.from_axis_angle(Vec3(0, 1, 0), math.radians(0.8)))
    _plate(engine, "bad", Quat.from_axis_angle(Vec3(0, 1, 0), math.radians(2.0)))

    def accepted(subject: str):
        return evaluate(
            engine,
            AcceptanceQuery(
                query_id=subject,
                description="mounted face follows its host",
                metric=MetricKind.SURFACE_ANGLE,
                subject=f"roof|{subject}",
                expected=0.0,
                tolerance=1.0,
                comparison=Comparison.EQ,
            ),
        )

    assert accepted("good").passed
    assert not accepted("bad").passed


def test_surface_angle_is_an_agent_visible_measurement() -> None:
    spec = next(spec for spec in MEASURE_SPECS if spec.name == "measure_surface_angle")

    assert spec.handler is not None
    assert spec.mutating is False
