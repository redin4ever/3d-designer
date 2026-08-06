"""Tests for the phase machine, the promotion gate, and tool-role partitioning
(ADR-012, ADR-013, ADR-007, ADR-003, ADR-005).

A phase hands off when its acceptance queries pass against live geometry, never when an
agent says it is finished (ADR-005) — agents self-report false success in 13-89% of
failures, and a second agent reviewing that claim catches it barely above chance.

**ADR-012 removed the override.** Three tests in this file previously asserted that
``promote(force=True)`` overrode a failing check and recorded the override. They are gone,
replaced by the tests below, because the behaviour they describe was deleted at Gate B 1.1
by an accepted ADR — ``PhasePromotion.allow_override`` no longer exists in the frozen
contract either. That is the one legitimate reason to retire a test: not "it was
inconvenient", but "the requirement it encoded was superseded in writing".
"""

from __future__ import annotations

import pytest

from contracts import (
    PHASE_ORDER,
    AcceptanceResult,
    Operation,
    Phase,
    ToolRole,
    Vec3,
)
from orchestration import Orchestrator, PromotionRefused


def _build_one_clean_box(scene, orch: Orchestrator, object_id: str = "box") -> None:
    """The minimum a blockout genuinely needs: one manifold object with applied transforms.

    Goes through ``perform`` rather than touching the engine, so the log and the geometry
    agree — which is what the promotion gate is about to read.
    """
    lease = orch.acquire("writer", Phase.BLOCKOUT)
    orch.perform(
        Operation(op_id=f"op-{object_id}", kind="add_cube", produced_objects=(object_id,)),
        lease,
    )
    orch.release(lease)


def test_orchestrator_starts_in_blockout(scene) -> None:
    """Blockout is deliberately the starting phase — primitives, proportion, placement, no
    detail. A run that began anywhere else would skip the stage every later pass exists to
    convert, which is the "stitched together" failure this product answers."""
    orch = Orchestrator(scene)

    assert orch.phase is Phase.BLOCKOUT
    assert tuple(PHASE_ORDER) == (Phase.BLOCKOUT, Phase.REFINE, Phase.DETAIL, Phase.POLISH)


def test_can_promote_is_false_with_the_failing_queries_on_a_fresh_scene(scene) -> None:
    """A fresh scene has produced no geometry at all, so real acceptance queries for
    "blockout is complete" cannot pass. ``can_promote`` returning a bare ``False`` with no
    ``AcceptanceResult`` to explain it would leave an agent guessing what to fix — Gate A
    4.2 requires the agent be told which rule broke, never left to infer it."""
    orch = Orchestrator(scene)

    can, results = orch.can_promote()

    assert can is False
    assert results != ()
    assert all(isinstance(r, AcceptanceResult) for r in results)
    assert any(r.passed is False for r in results)


def test_can_promote_evaluates_live_geometry_not_the_operation_count(scene) -> None:
    """What shipped in pass 1 computed ``passed = len(produced_this_phase) > 0`` — "did
    anything happen at all" — and ``measure.evaluate`` had zero non-test call sites anywhere
    in the product. Under that rule a phase full of broken geometry promoted as readily as a
    finished one, and ADR-005's "a definition of done is a re-run measurement, not a claim"
    was contradicted by the only code that claimed to implement it."""
    orch = Orchestrator(scene)
    lease = orch.acquire("writer", Phase.BLOCKOUT)
    orch.perform(Operation(op_id="op-1", kind="add_cube", produced_objects=("box",)), lease)
    orch.release(lease)

    # An operation was recorded, so the old placeholder rule would say yes here.
    scene.engine.delete("box")

    can, results = orch.can_promote()

    assert can is False
    assert any(not r.passed for r in results)


def test_a_failing_result_names_subject_actual_expected_and_a_concrete_fix(scene) -> None:
    """ADR-012 removed the override, so a refusal is the *only* thing an unattended agent
    has to work from. A failure that does not say which object, what was measured, what was
    required and which call would fix it is a dead end with nobody watching — the mitigation
    the user was told about at the gate before choosing the strictest option."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)
    _make_non_manifold(scene.engine, "box")

    can, results = orch.can_promote()
    failures = [r for r in results if not r.passed]

    assert can is False
    assert failures != []
    for failure in failures:
        assert failure.subject, f"{failure.query_id} names no object"
        assert failure.actual is not None, f"{failure.query_id} reports no measured value"
        assert failure.expected is not None, f"{failure.query_id} reports no threshold"
        assert failure.suggested_operation, f"{failure.query_id} suggests no operation"
        assert "(" in failure.suggested_operation and ")" in failure.suggested_operation, (
            f"{failure.query_id} suggests {failure.suggested_operation!r}, which is advice "
            "rather than a call an agent can make"
        )
    assert any("split_non_manifold(object_id='box')" == f.suggested_operation for f in failures)


def test_promote_refuses_while_the_current_phases_queries_fail(scene) -> None:
    """The gate. If promotion succeeded anyway, the blockout → refine → detail → polish plan
    would remain what Phase 6 measured it to be: advisory in the strictest sense, with
    nothing anywhere enforcing ordering."""
    orch = Orchestrator(scene)

    with pytest.raises(PromotionRefused) as exc:
        orch.promote()

    assert orch.phase is Phase.BLOCKOUT
    assert "blockout" in str(exc.value)


def test_promote_succeeds_once_the_queries_pass(scene) -> None:
    """The mirror image, and the one that keeps the gate usable: a phase whose acceptance
    queries genuinely pass must hand off. A query set that cannot be satisfied is a
    product-stopping defect under ADR-012, not a cosmetic one, because the run has no
    override left to escape with."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)

    can, results = orch.can_promote()
    assert can is True, [r.describe() for r in results if not r.passed]

    assert orch.promote() is Phase.REFINE
    assert orch.phase is Phase.REFINE


def test_promote_no_longer_accepts_a_force_argument(scene) -> None:
    """ADR-012 removed the override rather than discouraging it. Leaving the parameter in
    place — even defaulting to ``False`` — would leave the escape hatch one keyword away for
    any agent that reads the signature, which is precisely the gap between "discouraged" and
    "removed" the user chose against at Gate B 1.1."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)

    with pytest.raises(TypeError):
        orch.promote(force=True)


def test_a_promotion_is_recorded_in_the_operation_log(scene) -> None:
    """An operator reviewing a run later must be able to see when each phase handed off and
    what was checked. Promotion routes through the log ``scene`` already keeps rather than a
    second audit channel, so the live view's existing subscriber sees it too."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)

    orch.promote()

    promotions = [op for op in scene.document.operations if op.kind == "phase_promotion"]
    assert len(promotions) == 1
    assert promotions[0].params["from"] == "blockout"
    assert promotions[0].params["to"] == "refine"
    assert promotions[0].params["checked"], "the promotion recorded no queries it checked"


def test_promoting_past_polish_raises(scene) -> None:
    """``POLISH`` is the last entry in ``PHASE_ORDER``; there is nothing to promote to. An
    implementation that let this call succeed would produce a phase value that exists
    nowhere in the professional progression this product models, and every downstream
    consumer of ``Phase`` would have to guard against it forever after."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)
    scene.document.phase = Phase.POLISH

    with pytest.raises(ValueError):
        orch.promote()


def test_detail_phase_damage_is_repairable_from_detail_and_the_loop_closes(scene) -> None:
    """The deadlock ADR-012 created and ``PHASE_ROLES`` mitigates, tested end to end: break
    it, repair it, promote. A detail-phase operation that leaves a non-manifold edge must be
    fixable *from detail*. If it were not, the phase could never pass its own acceptance
    query and — with no override left — an unattended run would be stranded there with
    nobody to redirect it. This is the single most expensive failure ADR-012 can produce."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)
    scene.document.phase = Phase.DETAIL

    _make_non_manifold(scene.engine, "box")
    broken, results = orch.can_promote()
    assert broken is False
    assert any("split_non_manifold" in r.suggested_operation for r in results if not r.passed)

    # The repair a REPAIR-role tool performs, which PHASE_ROLES keeps legal in DETAIL.
    lease = orch.acquire("repairer", Phase.DETAIL, roles=(ToolRole.REPAIR,))
    orch.authorize("split_non_manifold", (ToolRole.REPAIR,), lease)
    scene.engine.delete("box")
    scene.engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    repaired, results = orch.can_promote()
    assert repaired is True, [r.describe() for r in results if not r.passed]
    assert orch.promote() is Phase.POLISH


def test_polish_demands_uvs_and_says_how_to_get_them(scene) -> None:
    """Polish is where UV, bake, LOD and budget live. A polish phase that promotes without
    UVs would let an unwrapped asset reach export, which is the one place the failure becomes
    someone else's problem — an import error in an engine rather than a warning here."""
    orch = Orchestrator(scene)
    _build_one_clean_box(scene, orch)
    scene.document.phase = Phase.POLISH

    can, results = orch.can_promote()
    unwrap = [r for r in results if not r.passed and "unwrap_uvs" in r.suggested_operation]

    assert can is False
    assert unwrap != []
    assert unwrap[0].subject == "box"

    scene.engine.unwrap("box")
    can, results = orch.can_promote()
    assert can is True, [r.describe() for r in results if not r.passed]


# ---------------------------------------------------------------------- tool partitioning


def test_tools_for_only_ever_narrows_what_the_registry_published(scene) -> None:
    """``tools_for`` filters; it must never add. The bound on how many tools a role may see
    at all (ADR-003's accuracy-optimal visible set) is registry *policy* and belongs to
    ``mcp_server`` — ``ARCHITECTURE.md`` puts content beside each operation and policy there,
    and Gate B 3.3 deliberately let ``inspect`` exceed the band and recorded it. What this
    module owns is the promise that anything it shows is something the registry published and
    the phase permits; a tool invented here would be a call ``dispatch`` then refuses."""
    from mcp_server import tools_for as registry_tools_for

    orch = Orchestrator(scene)

    for phase in PHASE_ORDER:
        scene.document.phase = phase
        for role in ToolRole:
            # Compared by name: ``ToolSpec`` carries a JSON-schema dict and so is not
            # hashable, and the name is what an agent actually calls anyway.
            visible = {spec.name for spec in orch.tools_for(role)}
            assert visible <= {spec.name for spec in registry_tools_for(role)}, (role, phase)


def test_tools_for_returns_real_tools_that_dispatch_would_actually_accept(scene) -> None:
    """The fictional table this replaced listed 16 tool names, **none** of which matched any
    of the 29 real ones — ``close_gap`` against the real ``close_visual_gap``, every entry
    carrying an empty input schema. ``tools_for`` is the method a phase-aware "what can I do
    now" query calls, so every name it returned was a call that would fail."""
    from mcp_server import tools_for as registry_tools_for

    orch = Orchestrator(scene)
    real = {spec.name for role in ToolRole for spec in registry_tools_for(role)}

    scene.document.phase = Phase.BLOCKOUT
    names = {spec.name for spec in orch.tools_for(ToolRole.BLOCKOUT)}

    assert names != set()
    assert names <= real
    assert "add_primitive" in names


def test_tools_for_hides_tools_that_are_not_legal_in_the_current_phase(scene) -> None:
    """ADR-013: "what can I do now" and "what will actually be accepted" have to be the same
    answer. A tool listed as available and then refused by ``authorize`` teaches an agent
    that refusals are noise, and it retries them."""
    orch = Orchestrator(scene)

    scene.document.phase = Phase.BLOCKOUT
    assert orch.tools_for(ToolRole.POLISH) == ()
    assert orch.tools_for(ToolRole.BLOCKOUT) != ()

    scene.document.phase = Phase.POLISH
    assert orch.tools_for(ToolRole.POLISH) != ()
    assert orch.tools_for(ToolRole.BLOCKOUT) == ()


def test_tools_for_inspect_returns_only_non_mutating_tools(scene) -> None:
    """A single mutating tool reaching an INSPECT-role agent breaks the concurrency
    guarantee the whole multi-agent design rests on: many INSPECT agents run concurrently
    *precisely because* none of their tools can mutate (ADR-007)."""
    orch = Orchestrator(scene)

    for phase in PHASE_ORDER:
        scene.document.phase = phase
        assert all(spec.mutating is False for spec in orch.tools_for(ToolRole.INSPECT))


def test_tools_for_can_be_given_a_registry_at_construction(scene) -> None:
    """``ARCHITECTURE.md``'s dependency arrow runs ``scene → orchestration → mcp``. Sourcing
    the registry by importing ``mcp_server`` here would reverse it, so the composition root
    can hand one in instead — the same direction every other dependency in this module
    travels."""
    from contracts import ToolSpec

    spec = ToolSpec(
        name="add_primitive",
        description="injected",
        roles=(ToolRole.BLOCKOUT,),
        input_schema={"type": "object", "properties": {}},
    )
    orch = Orchestrator(scene, registry={ToolRole.BLOCKOUT: (spec,)})

    assert orch.tools_for(ToolRole.BLOCKOUT) == (spec,)
    assert orch.tools_for(ToolRole.REPAIR) == ()


def _make_non_manifold(engine, object_id: str) -> None:
    """Replace ``object_id`` with a mesh whose edge 0-1 carries three faces.

    Stands in for a detail-phase operation that leaves a fan behind — the case ADR-012's
    no-override gate can strand a run on.
    """
    engine.delete(object_id)
    engine.create_mesh(
        object_id,
        [
            Vec3(0.0, 0.0, 0.0),
            Vec3(1.0, 0.0, 0.0),
            Vec3(0.5, 1.0, 0.0),
            Vec3(0.5, -1.0, 0.0),
            Vec3(0.5, 0.0, 1.0),
        ],
        [(0, 1, 2), (0, 1, 3), (0, 1, 4)],
    )
