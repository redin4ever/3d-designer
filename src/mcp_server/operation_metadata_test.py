"""MCP dispatch persists semantic acceptance and intentional overlap metadata."""

from __future__ import annotations

from contracts import Phase
from mcp_server import dispatch


def test_dispatch_persists_runtime_acceptance_on_a_normal_operation(
    orchestrator, write_lease, fake_scene,
) -> None:
    dispatch(
        "add_primitive", {"object_id": "box", "kind": "cube", "size": [1, 1, 1]},
        orchestrator=orchestrator, lease=write_lease,
    )

    logged = fake_scene.document.operations[-1]
    assert logged.acceptance
    assert logged.acceptance[0].subject == "box"


def test_dispatch_persists_gable_roof_joint_acceptance(
    orchestrator, write_lease, fake_scene,
) -> None:
    dispatch(
        "add_gable_roof",
        {
            "object_id": "roof", "origin": [0, 0, 2.8], "width": 6.0, "depth": 8.0,
            "pitch_degrees": 32.0, "thickness": 0.18, "overhang": 0.4,
            "trim_width": 0.14, "trim_depth": 0.18, "ridge_axis": "y",
        },
        orchestrator=orchestrator, lease=write_lease,
    )

    logged = fake_scene.document.operations[-1]
    assert len(logged.acceptance) == 9
    assert len(logged.joinery) == 2
    assert all("|" in query.subject for query in logged.acceptance)


def test_dispatch_persists_stair_stringer_joinery_and_landing_acceptance(
    orchestrator, fake_scene,
) -> None:
    fake_scene.document.phase = Phase.REFINE
    lease = orchestrator.acquire(holder="refiner", phase=Phase.REFINE)
    dispatch(
        "add_staircase_to_landing",
        {
            "object_id": "entry", "landing_id": "porch", "start": [0, -3, 0],
            "treads": 6, "width": 1.4, "tread_thickness": 0.05,
            "stringer_width": 0.12, "stringer_depth": 0.2,
        },
        orchestrator=orchestrator, lease=lease,
    )

    logged = fake_scene.document.operations[-1]
    assert logged.acceptance[0].subject == "entry_tread_005|porch"
    assert len(logged.joinery) == 12
