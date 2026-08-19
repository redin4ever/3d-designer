from __future__ import annotations

import math

import pytest

from contracts import MetricKind, Operation, Quat, ToolError, Transform, Vec3
from measure import surface_angle
from testing import FakeEngine

from .surface_mounts import add_roof_window, add_wall_sign
from .surface_frame import roof_frame
from .validation import acceptance_for


def _sloped_roof(engine: FakeEngine) -> None:
    engine.create_primitive(
        "roof", "cube", Vec3(8, 5, 0.2),
        Transform(rotation=Quat.from_axis_angle(Vec3(0, 1, 0), math.radians(24))),
    )


def test_roof_window_derives_its_orientation_from_the_host_surface() -> None:
    engine = FakeEngine()
    _sloped_roof(engine)
    result = add_roof_window(engine, Operation("rw", "add_roof_window", {
        "object_id": "skylight", "roof_id": "roof", "width": 2.0, "height": 1.2,
        "frame_width": 0.10, "depth": 0.08,
        "horizontal_fraction": 0.5, "vertical_fraction": 0.5,
    }))
    assert result.produced_objects == ("skylight_glass", "skylight_frame")
    assert surface_angle(engine, "roof", "skylight_glass").value == pytest.approx(0, abs=1e-6)


def test_oversize_roof_window_is_rejected_without_partial_geometry() -> None:
    engine = FakeEngine()
    _sloped_roof(engine)
    before = engine.list_objects()
    with pytest.raises(ToolError, match="does not fit"):
        add_roof_window(engine, Operation("rw", "add_roof_window", {
            "object_id": "huge", "roof_id": "roof", "width": 20.0, "height": 1.2,
            "frame_width": 0.10, "depth": 0.08,
            "horizontal_fraction": 0.5, "vertical_fraction": 0.5,
        }))
    assert engine.list_objects() == before


def test_wall_sign_is_centered_at_the_requested_height_and_faces_toward_point() -> None:
    engine = FakeEngine()
    engine.create_primitive("wall", "cube", Vec3(10, 0.2, 5), Transform(translation=Vec3(0, 0, 2.5)))
    result = add_wall_sign(engine, Operation("sign", "add_wall_sign", {
        "object_id": "factory_sign", "wall_id": "wall", "text": "FORGE WORKS",
        "toward": Vec3(0, -10, 2), "center_height": 4.1,
        "height": 0.65, "depth": 0.08, "edge_margin": 0.4,
    }))
    bounds = engine.world_bounds(result.produced_objects[0])
    assert bounds.centre.x == pytest.approx(0, abs=1e-6)
    assert bounds.centre.z == pytest.approx(4.1, abs=1e-6)
    assert surface_angle(engine, "wall", "factory_sign").value == pytest.approx(0, abs=1e-6)


def test_wall_sign_that_does_not_fit_is_atomic() -> None:
    engine = FakeEngine()
    engine.create_primitive("wall", "cube", Vec3(2, 0.2, 2), Transform(translation=Vec3(0, 0, 1)))
    before = engine.list_objects()
    with pytest.raises(ToolError, match="does not fit"):
        add_wall_sign(engine, Operation("sign", "add_wall_sign", {
            "object_id": "bad", "wall_id": "wall", "text": "FORGE WORKS",
            "toward": Vec3(0, -10, 1), "center_height": 1.0,
            "height": 1.0, "depth": 0.08, "edge_margin": 0.2,
        }))
    assert engine.list_objects() == before


def test_surface_operations_publish_orientation_and_contact_acceptance() -> None:
    roof_queries = acceptance_for("add_roof_window", {"object_id": "light", "roof_id": "roof"})
    sign_queries = acceptance_for("add_wall_sign", {"object_id": "sign", "wall_id": "wall"})
    assert {query.metric for query in roof_queries} == {MetricKind.SURFACE_ANGLE, MetricKind.GAP_WIDTH}
    assert {query.metric for query in sign_queries} == {MetricKind.SURFACE_ANGLE, MetricKind.GAP_WIDTH}


def test_surface_detection_ignores_near_degenerate_tessellation_slivers() -> None:
    engine = FakeEngine()
    engine.create_mesh(
        "roof",
        [Vec3(-1, -1, 0), Vec3(1, -1, 0), Vec3(1, 1, 0), Vec3(-1, 1, 0),
         Vec3(0, 0, 0), Vec3(0.003, 0, 0), Vec3(0, 0.003, 0)],
        [(0, 1, 2), (0, 2, 3), (4, 5, 6)],
    )
    assert roof_frame(engine, "roof").width == pytest.approx(2.0)
