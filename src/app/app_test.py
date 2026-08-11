"""End-to-end tests for the composition root.

Every other suite tests one module against a fake. This one drives the whole stack the way
an agent would — registry, write lock, scene log, real handlers, real measurement, real
export — and is the only place that can catch a wire that was never connected. Sixteen
green modules that do not talk to each other is the failure mode this file exists to find.

The Blender-backed tests are marked ``needs_blender`` and skip automatically without it.
The rest run on the in-memory engine, so the wiring itself stays verifiable anywhere.
"""

from __future__ import annotations

import pytest

from contracts import (
    CheckCadence,
    DefectClass,
    JoineryIntent,
    Operation,
    Phase,
    ToolRole,
    Vec3,
)

from app import build_app, build_handlers


RECORDED_TOOL_COUNTS: dict[str, int] = {
    # blockout and refine both gained the seven direct edits added at Q-14 — move, rotate,
    # scale, delete, duplicate, rename, set material. Updated deliberately, which is the
    # measurement Gate B 3.3 asked for; not capped, which is the one response ruled out.
    "blockout": 17,
    "refine": 16,
    "repair": 8,
    "align": 7,
    "detail": 8,
    "polish": 6,
    # +1: get_operator_context (Q-03) — the tool that returns an annotation image,
    # which an ActionReport is text and cannot carry.
    "inspect": 11,
    "export": 2,
    "admin": 2,
}
"""The real per-role visible-tool counts, as assembled by the composition root.

Gate B 3.3 chose to exceed the 5-8 accuracy-optimal band deliberately and measure it rather
than split roles further or cap the visible set. ``inspect`` is the one role over, at 9 —
``measure``'s six tools plus ``get_phase``/``list_objects``/``describe_object``.

Duplicated on purpose from ``mcp_server/registry_test.py``: that one records what the
registry *builds*, this one records what the wired application actually *exposes*. They
have disagreed before — a fair-capping fallback once trimmed each role to eight and silently
dropped ``repair``, ``make_plumb`` and ``close_visual_gap`` — and two independent ledgers
are how that becomes a test failure instead of three missing operations.
"""


# --------------------------------------------------------------------- wiring

def test_the_handler_registry_is_not_empty() -> None:
    """`scene` replays by looking each Operation.kind up in this registry. If it is empty
    every agent tool call resolves to nothing, and the whole system is inert while every
    module's own suite stays green."""
    handlers = build_handlers()
    assert handlers, "no operations registered — nothing can be built"


def test_every_operation_module_reaches_the_registry() -> None:
    """Each module was built in isolation with its own calling convention. A module whose
    adapter is missing loses all of its tools silently."""
    handlers = build_handlers()
    for kind in (
        "add_railing",        # ops
        "add_gable_roof",     # semantic architectural blockout
        "add_staircase_to_landing",  # relation-derived architectural refine
        "repair",             # gaps
        "make_plumb",         # align
        "apply_edge_treatment",  # detail
        "unwrap_uvs",         # uv
        "raw_execute",        # raw
    ):
        assert kind in handlers, f"{kind} is not registered — its module is unreachable"


def test_no_operation_module_is_missing() -> None:
    """A guarded import that swallowed a real breakage would show up here rather than as
    an agent getting 'unknown operation' halfway through a build."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    assert app.missing == (), f"unavailable modules: {app.missing}"


def test_every_registered_tool_is_executable_by_one_route_or_the_other() -> None:
    """A tool an agent can see but nothing can execute fails at call time, after the agent
    has already committed to a plan.

    This test used to carve ``export_scene`` and ``check_export_budget`` out of its own
    assertion, with no comment — so the one check written to catch "visible but not
    executable" excluded the two tools that were exactly that, and export raised a raw
    ``KeyError`` through the only path an agent has. There is no carve-out now.

    There are two legitimate routes: an operation kind in ``app.handlers``, which is
    replayable and lands in the undo log, and a ``ToolSpec.handler`` callable, which is
    invoked directly and does not (ADR-014). Export, the session tools and the measurement
    tools all take the second. A tool with neither is the defect.
    """
    app = build_app(prefer_blender=False, attach_viewer=False)
    unreachable = sorted(
        t.name
        for tools in app.registry.values()
        for t in tools
        if t.name not in app.handlers and t.handler is None
    )
    assert unreachable == [], f"tools an agent can see but cannot execute: {unreachable}"


def test_the_per_role_tool_counts_are_the_ones_that_were_recorded() -> None:
    """Gate B 3.3 chose to exceed the 5-8 accuracy-optimal band deliberately and *measure*
    it, rather than split roles further or cap the visible set.

    That choice only means something if the number is written down where it fails when it
    drifts — otherwise "we exceeded it on purpose" and "it grew while nobody was looking"
    are indistinguishable. A fair-capping fallback once silently hid ``repair``,
    ``make_plumb`` and ``close_visual_gap``, which are core operations; capping is the one
    response that is not allowed here.

    If this fails because you added a tool: update the number, and say so in the pipeline
    summary. Do not add a cap.
    """
    app = build_app(prefer_blender=False, attach_viewer=False)
    actual = {role.value: len(tools) for role, tools in app.registry.items()}
    assert actual == RECORDED_TOOL_COUNTS


def test_nothing_hides_a_tool_from_the_role_that_declares_it() -> None:
    """The failure the recorded counts exist to prevent: a registry that quietly drops
    tools to stay inside a bound leaves an agent unable to call an operation it was never
    told about, and no error anywhere says so."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    exposed = {t.name for tools in app.registry.values() for t in tools}
    for module_tools in (app.registry.values()):
        for tool in module_tools:
            assert tool.name in exposed


def test_inspect_role_gets_no_mutating_tool() -> None:
    """Many inspect agents run concurrently precisely because none of their tools can
    mutate. One mutating tool here breaks the guarantee the multi-agent design rests on."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    for tool in app.registry.get(ToolRole.INSPECT, ()):
        assert not tool.mutating, tool.name


def test_the_scene_exposes_its_engine_so_measurements_can_run() -> None:
    """B-000: without this, the check-after-every-geometry-change loop had no route to
    geometry and carried placeholder measurements — the user's Gate A 3.1 answer silently
    not running."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    assert app.scene.engine is app.engine


def test_cadence_is_persisted_on_the_document_and_changeable() -> None:
    """The user asked for a settings control that changes this mid-run, in their own words."""
    app = build_app(prefer_blender=False, attach_viewer=False, cadence=CheckCadence.PHASE_BOUNDARIES)
    assert app.scene.document.check_cadence is CheckCadence.PHASE_BOUNDARIES
    app.orchestrator.set_cadence(CheckCadence.EVERY_GEOMETRY_CHANGE)
    assert app.orchestrator._cadence is CheckCadence.EVERY_GEOMETRY_CHANGE  # noqa: SLF001


def test_describe_says_which_engine_it_is_on() -> None:
    """Running on the fake is legitimate for a smoke test and useless for an asset. The
    difference has to be visible at startup, not discovered on export."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    assert "fake" in app.describe()


# ------------------------------------------------------- the journey, end to end

def _apply(app, op_kind: str, op_id: str, **params) -> object:
    """Drive one operation the way an agent would: take the lock, apply, release.

    ``op_kind`` rather than ``kind`` because several operations take a ``kind`` parameter
    of their own (``add_primitive(kind="cube")``) and a collision here would silently
    shadow it.
    """
    lease = app.orchestrator.acquire("test-writer", app.orchestrator.phase)
    try:
        return app.scene.apply(Operation(op_id=op_id, kind=op_kind, params=params), lease=lease)
    finally:
        app.orchestrator.release(lease)


@pytest.mark.needs_blender
def test_a_staircase_and_railing_come_out_of_the_real_stack() -> None:
    """The user's own example, through the real path: registry -> lock -> log -> handler
    -> Blender. If this fails, the product does not do the thing it was built for."""
    app = build_app(prefer_blender=True, attach_viewer=False)
    assert app.backend.startswith("bpy"), "this test is meaningless on the fake"

    stair = _apply(app, "add_staircase", "op-stair", object_id="stair", treads=12,
                   rise=0.18, run=0.28, width=1.0)
    assert stair.ok, f"{stair.error_rule}: {stair.error_detail}"
    assert stair.produced_objects, "a staircase produced no geometry"

    rail = _apply(app, "add_railing", "op-rail", object_id="rail",
                  path=[[0.0, 0.0, 0.0], [3.36, 0.0, 2.16]],
                  height=0.95, post_spacing=1.0, baluster_gap=0.09)
    assert rail.ok, f"{rail.error_rule}: {rail.error_detail}"
    assert rail.produced_objects, "a railing produced no geometry"


@pytest.mark.needs_blender
def test_every_railing_post_stands_plumb_on_a_rake() -> None:
    """Posts normal to the stair rake instead of vertical is *the* classic naive-generator
    error and the single most visible thing this product exists to get right. Checked
    through the whole stack, not against the module in isolation."""
    from contracts import WORLD_UP

    app = build_app(prefer_blender=True, attach_viewer=False)
    result = _apply(app, "add_railing", "op-rail", object_id="rail",
                    path=[[0.0, 0.0, 0.0], [3.0, 0.0, 1.8]],
                    height=0.95, post_spacing=0.9, baluster_gap=0.09)
    assert result.ok, f"{result.error_rule}: {result.error_detail}"

    posts = [o for o in result.produced_objects if "post" in o]
    assert posts, f"no posts among {result.produced_objects}"
    for post in posts:
        up = app.engine.snapshot(post).transform.rotation.rotate(Vec3(0, 0, 1)).normalized()
        assert up.z == pytest.approx(WORLD_UP.z, abs=1e-4), f"{post} leans (up.z={up.z:.4f})"


@pytest.mark.needs_blender
def test_measurement_runs_against_the_real_scene_after_an_operation() -> None:
    """The product's core promise: the tool computes the spatial facts so the model never
    eyeballs them. A report with no measurements means the promise is not being kept."""
    import measure

    app = build_app(prefer_blender=True, attach_viewer=False)
    _apply(app, "add_primitive", "op-box", object_id="box", kind="cube",
           size=[2.0, 4.0, 1.0])

    dims = measure.dimensions(app.engine, "box")
    assert dims.value[0] == pytest.approx(2.0, abs=1e-3)
    assert dims.value[1] == pytest.approx(4.0, abs=1e-3)


@pytest.mark.needs_blender
def test_clipping_is_detected_and_declared_joinery_silences_it() -> None:
    """Distinguishing a post correctly socketed into a deck from two posts wrongly
    overlapping is the capability the user named, and no library can infer it from
    geometry — it has to be declared. Verified through the wired stack."""
    import measure

    app = build_app(prefer_blender=True, attach_viewer=False)
    _apply(app, "add_primitive", "op-a", object_id="a", kind="cube", size=[1.0, 1.0, 1.0])
    _apply(app, "add_primitive", "op-b", object_id="b", kind="cube", size=[1.0, 1.0, 1.0])
    app.engine.set_transform("b", app.engine.snapshot("b").transform.__class__(
        translation=Vec3(0.97, 0, 0)))

    defects = measure.find_clipping(app.engine, [("a", "b")])
    assert any(d.defect_class is DefectClass.PART_CLIPPING for d in defects), \
        "a 30mm interpenetration went undetected"

    permitted = measure.find_clipping(
        app.engine, [("a", "b")],
        joinery=[JoineryIntent(object_id="b", into_object_id="a", depth=0.05)],
    )
    assert permitted == (), "a declared socket was still reported as a clipping bug"


@pytest.mark.needs_blender
def test_a_model_exports_for_roblox_with_the_conversion_applied() -> None:
    """The user's usual engine. An export that silently drops the unit conversion arrives
    at 1/0.28 of its intended size, which is discovered in Roblox rather than here."""
    import export

    app = build_app(prefer_blender=True, attach_viewer=False)
    _apply(app, "add_primitive", "op-box", object_id="box", kind="cube", size=[2.8, 2.8, 2.8])

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "out.glb")
        report = export.export_scene(app.engine, ["box"], path, profile_name="roblox")
        assert report.ok
        assert Path(report.path).exists() and Path(report.path).stat().st_size > 0
        assert "roblox" in report.banner.lower()


# ------------------------------------------------------------------ the loop

def test_the_write_lock_is_enforced_through_the_wired_stack() -> None:
    """Exactly one writer is the safety property the multi-agent design rests on. Tested
    here against the real Scene rather than a per-module double."""
    from contracts import LockContention

    app = build_app(prefer_blender=False, attach_viewer=False)
    lease = app.orchestrator.acquire("writer-a", Phase.BLOCKOUT)
    with pytest.raises(LockContention):
        app.orchestrator.acquire("writer-b", Phase.BLOCKOUT)
    app.orchestrator.release(lease)
    app.orchestrator.acquire("writer-b", Phase.BLOCKOUT)  # now free


def test_undo_is_a_pointer_move_through_the_wired_stack() -> None:
    """No existing tool has undo; the user named losing work as an abandonment trigger."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    _apply(app, "add_primitive", "op-1", object_id="one", kind="cube", size=[1.0, 1.0, 1.0])
    _apply(app, "add_primitive", "op-2", object_id="two", kind="cube", size=[1.0, 1.0, 1.0])
    assert app.scene.document.head == 2

    app.scene.undo(1)

    assert app.scene.document.head == 1
    assert not app.engine.exists("two"), "undo left the object behind"
    assert app.engine.exists("one"), "undo removed more than it should have"


def test_a_viewer_receives_events_from_a_real_operation() -> None:
    """The live view is how the user watches an autonomous run. A bridge that attaches but
    never receives leaves them staring at an empty viewport with no error."""
    app = build_app(prefer_blender=False, attach_viewer=True)
    if app.viewer is None:
        pytest.skip("viewer unavailable in this environment")
    _apply(app, "add_primitive", "op-1", object_id="one", kind="cube", size=[1.0, 1.0, 1.0])
    assert app.viewer.pending(), "the viewer saw nothing after an operation was applied"


# ------------------------------------------------- the real agent path, end to end
#
# Five independent QA finders reported the same P0 here: `Orchestrator.perform` never
# forwarded the caller's lease to `Scene.apply`, so every mutating call through the agent
# path raised LockContention against the lease it had just verified. It survived every
# module suite because both FakeScene doubles implemented `apply(self, op)` with no lock
# check at all — a double agreeing with the wrong side of the contract.
#
# These tests use the REAL Orchestrator against the REAL Scene. That is the only
# arrangement that could have caught it.

def test_perform_reaches_the_engine_with_the_lease_it_just_verified() -> None:
    """The whole agent-facing pipeline. If this fails, no tool call can change anything."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    lease = app.orchestrator.acquire("writer", app.orchestrator.phase)

    report = app.orchestrator.perform(
        Operation(op_id="op-1", kind="add_primitive",
                  params={"object_id": "box", "kind": "cube", "size": [1.0, 1.0, 1.0]}),
        lease,
    )

    assert report.ok, f"{report.error_rule}: {report.error_detail}"
    assert app.engine.exists("box"), "the operation reported success but made no geometry"


def test_perform_carries_real_measurements_not_placeholders() -> None:
    """Gate A 3.1 and ADR-005: the tool computes the spatial facts so the model never
    eyeballs them. This emitted a hardcoded triangle count of 0.0 for every operation
    while reading as a working check-after-every-change loop."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    lease = app.orchestrator.acquire("writer", app.orchestrator.phase)

    report = app.orchestrator.perform(
        Operation(op_id="op-1", kind="add_primitive",
                  params={"object_id": "box", "kind": "cube", "size": [2.0, 4.0, 1.0]}),
        lease,
    )

    assert report.measurements, "no measurements — the check loop is not running"
    assert not report.checks_skipped
    dims = [m for m in report.measurements if m.kind.value == "dimensions"]
    assert dims, "no dimensions measured"
    assert dims[0].value[1] == pytest.approx(4.0, abs=1e-3), (
        f"measured {dims[0].value} — a placeholder would report zeros regardless of the object"
    )


def test_a_mutating_tool_call_through_dispatch_changes_the_model() -> None:
    """`dispatch` is the actual entry point an MCP client uses. Nothing tested it against
    a real Scene, so the lock bug was invisible from every module's own suite."""
    from mcp_server import dispatch

    app = build_app(prefer_blender=False, attach_viewer=False)
    lease = app.orchestrator.acquire("writer", ToolRole.BLOCKOUT and app.orchestrator.phase)

    dispatch(
        "add_primitive",
        {"object_id": "via_dispatch", "kind": "cube", "size": [1.0, 1.0, 1.0]},
        role=ToolRole.BLOCKOUT,
        orchestrator=app.orchestrator,
        lease=lease,
    )

    assert app.engine.exists("via_dispatch"), "a dispatched tool call produced no geometry"


def test_phase_promotion_can_actually_execute() -> None:
    """`promote` writes a phase_promotion operation into the log so an advance is recorded
    rather than silent. Nothing registered a handler for that kind, so `scene` raised
    KeyError and the phase machine — the backbone of the staged plan and of the
    single-writer design — could not advance at all.

    Rewritten for ADR-012: this used to pass ``force=True``, which no longer exists.
    Promotion now happens because the phase's acceptance queries actually passed, which is
    what Gate A 3.2 asked for and what pass 1 did not build. The old version asserted that
    a *forced* promotion was recorded; there is no forcing, so it asserted a requirement
    the gate has since superseded in writing.
    """
    app = build_app(prefer_blender=False, attach_viewer=False)
    lease = app.orchestrator.acquire("writer", app.orchestrator.phase)
    app.orchestrator.perform(
        Operation(op_id="op-1", kind="add_primitive",
                  params={"object_id": "box", "kind": "cube", "size": [1.0, 1.0, 1.0]}),
        lease,
    )

    passed, results = app.orchestrator.can_promote()
    assert passed, f"blockout should be passable with one clean cube: {results}"

    new_phase = app.orchestrator.promote()

    assert new_phase is Phase.REFINE
    assert app.scene.document.phase is Phase.REFINE
    recorded = [o for o in app.scene.document.operations if o.kind == "phase_promotion"]
    assert recorded, "the promotion was not recorded in the log"


def test_promotion_is_refused_when_the_phase_is_not_actually_finished() -> None:
    """The whole point of ADR-012. Pass 1 promoted as soon as *anything* had happened, so
    an agent walked blockout -> refine -> detail -> polish without a single quality check
    and `measure.evaluate` was never called anywhere in the product.

    With no override left, this refusal is also the only thing an unattended agent has to
    work from, so it has to say what failed and what would fix it.
    """
    app = build_app(prefer_blender=False, attach_viewer=False)
    passed, results = app.orchestrator.can_promote()

    assert not passed, "an empty scene should not pass blockout"
    failures = [r for r in results if not r.passed]
    assert failures, "refused, but named nothing that failed"
    assert any(r.suggested_operation for r in failures), (
        "a failing query named no operation that would fix it — an agent that cannot pass "
        "and cannot force has nothing left to try"
    )


# ------------------------------------------------------ QA round 2 regressions

def test_a_failed_operation_leaves_no_orphan_geometry() -> None:
    """`scene.apply`'s own contract says the engine must be exactly as observable as it
    was before a failed call. It was not: a handler that created geometry and then raised
    left it live and unlogged — one failed add_railing left 29 orphaned parts, which then
    appeared in the live view as geometry with no history and vanished on the next
    save/load."""
    from contracts import Vec3

    app = build_app(prefer_blender=False, attach_viewer=False)

    def half_then_fail(engine, op):
        engine.create_primitive("orphan_a", "cube", Vec3(1, 1, 1))
        engine.create_primitive("orphan_b", "cube", Vec3(1, 1, 1))
        raise RuntimeError("failed after creating two objects")

    app.scene._handlers["half_then_fail"] = half_then_fail  # noqa: SLF001
    before = set(app.engine.list_objects())

    with pytest.raises(RuntimeError):
        app.scene.apply(Operation(op_id="op-boom", kind="half_then_fail"))

    assert set(app.engine.list_objects()) == before, "the failed handler left orphans behind"
    assert app.scene.document.head == 0, "a failed operation was recorded in the log"


def test_a_dead_writer_does_not_wedge_the_lock_forever() -> None:
    """Lease expiry was measured against document.head, which only advances when an
    operation is applied — which only the current holder can do. A holder that died
    mid-operation froze the clock at that moment, so its lease could never go stale and no
    other agent could ever acquire. Agents die (Rule 6); an autonomous run cannot recover
    from a permanently wedged lock."""
    from contracts import LockContention

    app = build_app(prefer_blender=False, attach_viewer=False)
    app.orchestrator.acquire("doomed", app.orchestrator.phase, ttl_ops=3)

    with pytest.raises(LockContention):
        app.orchestrator.acquire("successor", app.orchestrator.phase)

    # The doomed holder never applies anything and never releases — it is gone.
    for _ in range(5):
        try:
            app.orchestrator.acquire("successor", app.orchestrator.phase)
        except LockContention:
            continue
        break

    live = app.orchestrator.current()
    assert live is not None and live.holder == "successor", (
        "the lock never became reclaimable — the run is wedged permanently"
    )


def test_an_opaque_operation_records_a_barrier_with_a_real_snapshot() -> None:
    """SECURITY.md claims raw execution is recorded as an undo barrier with a real
    snapshot. Nothing in the wired product computed a snapshot_path, so an opaque operation
    either raised outright or recorded a barrier pointing at nothing — and undoing across
    it re-executed the arbitrary script instead of restoring."""
    from pathlib import Path

    app = build_app(prefer_blender=False, attach_viewer=False)
    lease = app.orchestrator.acquire("admin", app.orchestrator.phase)

    report = app.orchestrator.perform(
        Operation(op_id="op-raw", kind="raw_execute", opaque=True,
                  params={"source": "count = len(engine.list_objects())"}),
        lease,
    )

    assert report.ok, f"{report.error_rule}: {report.error_detail}"
    barrier = app.scene.document.barrier_before(0)
    assert barrier is not None, "an opaque operation recorded no undo barrier"
    assert barrier.snapshot_path, "the barrier has no snapshot to restore from"
    assert Path(barrier.snapshot_path.split("#")[0]).exists(), (
        f"barrier points at {barrier.snapshot_path}, which was never written"
    )
