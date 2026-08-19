from __future__ import annotations

from contracts import Operation, Vec3
from testing import FakeEngine

from .architecture import add_opening, add_wall
from .facade_ribs import add_facade_ribs


def test_facade_ribs_split_around_a_garage_opening_with_clearance() -> None:
    engine = FakeEngine()
    add_wall(engine, Operation("wall", "add_wall", {
        "object_id": "front", "start": Vec3(-5, 0, 0), "end": Vec3(5, 0, 0),
        "height": 5.0, "thickness": 0.2,
    }))
    add_opening(engine, Operation("door", "add_opening", {
        "object_id": "door", "wall_id": "front", "position": 5.0,
        "width": 4.0, "height": 3.0, "sill_height": 0.0,
    }))
    result = add_facade_ribs(engine, Operation("ribs", "add_facade_ribs", {
        "object_id": "front_ribs", "wall_id": "front", "toward": Vec3(0, -10, 2),
        "spacing": 1.0, "width": 0.08, "depth": 0.08, "edge_margin": 0.3,
        "opening_clearance": 0.05, "min_segment": 0.10,
    }))
    assert result.produced_objects == ("front_ribs",)
    verts = engine.snapshot("front_ribs").world_vertices()
    assert not [v for v in verts if abs(v.x) < 1.9 and v.z < 3.049]
