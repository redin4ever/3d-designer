"""Phase promotion enforces acceptance persisted on active operations."""

from __future__ import annotations

from contracts import AcceptanceQuery, Comparison, MetricKind, Operation, Phase, Transform, Vec3
from orchestration import Orchestrator


def _joint_query() -> AcceptanceQuery:
    return AcceptanceQuery(
        query_id="roof-op.roof_joint",
        description="the two roof panels meet at the ridge",
        metric=MetricKind.GAP_WIDTH,
        subject="roof_left|roof_right",
        expected=0.0,
        comparison=Comparison.EQ,
    )


def test_can_promote_enforces_active_operations_logged_acceptance(scene) -> None:
    orch = Orchestrator(scene)
    lease = orch.acquire("roofer", Phase.BLOCKOUT)
    orch.perform(
        Operation(
            op_id="roof-op", kind="add_gable_roof",
            produced_objects=("roof_left", "roof_right"),
            acceptance=(_joint_query(),),
        ),
        lease,
    )
    orch.release(lease)
    scene.engine.set_transform("roof_right", Transform(translation=Vec3(2, 0, 0)))

    can_promote, results = orch.can_promote()
    joint = next(result for result in results if result.query_id == "roof-op.roof_joint")

    assert can_promote is False
    assert joint.passed is False
    assert joint.subject == "roof_left|roof_right"
    assert joint.actual == 1.0
    assert joint.expected == 0.0
    assert joint.suggested_operation.startswith("close_visual_gap(")

    scene.engine.set_transform("roof_right", Transform(translation=Vec3(1, 0, 0)))
    can_promote, results = orch.can_promote()
    assert can_promote is True, [r.describe() for r in results if not r.passed]


def test_undone_operations_do_not_keep_the_phase_gated(scene) -> None:
    orch = Orchestrator(scene)
    lease = orch.acquire("roofer", Phase.BLOCKOUT)
    orch.perform(
        Operation(
            op_id="base", kind="add_cube", produced_objects=("base",),
        ),
        lease,
    )
    orch.perform(
        Operation(
            op_id="bad-roof", kind="add_gable_roof",
            acceptance=(_joint_query(),),
        ),
        lease,
    )
    orch.release(lease)
    scene.undo()

    can_promote, results = orch.can_promote()

    assert can_promote is True, [r.describe() for r in results if not r.passed]
    assert "roof-op.roof_joint" not in {result.query_id for result in results}

