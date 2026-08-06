"""Regression tests for the contract invariants.

Every test here corresponds to a finding from the Phase 4.2 contract review — a state that
was representable before the barrier ran, and would have been multiplied by fifteen
modules built against it. They are named after the failure, not the feature.
"""

from __future__ import annotations

import pytest

from contracts import (
    AABB,
    Anchor,
    AnchorKind,
    AssetClass,
    CheckCadence,
    Comparison,
    Conflict,
    Constraint,
    ConstraintKind,
    DEFAULT_SEVERITY,
    Defect,
    DefectClass,
    LockContention,
    Measurement,
    MeasurementReport,
    MeshSnapshot,
    MetricKind,
    Operation,
    Phase,
    Proposal,
    RollbackTarget,
    SceneDocument,
    Severity,
    ToolRole,
    ToolSpec,
    Transform,
    Vec3,
    WriteLease,
    epsilon_at,
    profile_for,
    reconcile_tolerance,
)
from contracts.wire import CadencePayload, RedirectPayload


# --------------------------------------------------------------------- geometry

def test_inverted_aabb_is_rejected() -> None:
    """An inverted box short-circuits overlaps() to False on its first inverted axis — a
    false negative in the broad-phase test that feeds clipping detection."""
    with pytest.raises(ValueError, match="inverted"):
        AABB(minimum=Vec3(5, 0, 0), maximum=Vec3(-5, 1, 1))


def test_triangle_index_outside_vertices_is_rejected() -> None:
    with pytest.raises(ValueError, match="indexes outside"):
        MeshSnapshot(object_id="o", vertices=[Vec3(), Vec3(1, 0, 0)], triangles=[(0, 1, 2)])


def test_normals_of_the_wrong_length_are_rejected() -> None:
    """zip(vertices, normals) truncates silently — later vertices get no normal, no error,
    and no signal that data went missing."""
    with pytest.raises(ValueError, match="normals for"):
        MeshSnapshot(
            object_id="o",
            vertices=[Vec3(), Vec3(1, 0, 0), Vec3(0, 1, 0)],
            triangles=[(0, 1, 2)],
            normals=[Vec3(0, 0, 1)],
        )


def test_polygon_count_is_derived_rather_than_defaulting_to_zero() -> None:
    """A zero here reports a heavy mesh as empty and defeats every budget warning."""
    snap = MeshSnapshot(
        object_id="o", vertices=[Vec3(), Vec3(1, 0, 0), Vec3(0, 1, 0)], triangles=[(0, 1, 2)]
    )
    assert snap.polygon_count == 1


def test_multi_material_mesh_must_say_which_triangle_uses_which() -> None:
    """Without per-triangle indices the viewer can only keep the first slot, which is a
    rendering bug that presents as a modelling bug."""
    with pytest.raises(ValueError, match="material slots"):
        MeshSnapshot(
            object_id="o",
            vertices=[Vec3(), Vec3(1, 0, 0), Vec3(0, 1, 0)],
            triangles=[(0, 1, 2)],
            material_slots=("metal", "paint"),
        )


def test_edges_have_a_canonical_order() -> None:
    """Edge indices are passed to bevel_edges as bare ints. Without one agreed ordering,
    a detail pass selects edge 7 and the engine bevels a different edge 7 — silently."""
    snap = MeshSnapshot(
        object_id="o",
        vertices=[Vec3(), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(1, 1, 0)],
        triangles=[(0, 1, 2), (1, 3, 2)],
    )
    edges = snap.edges()
    assert edges == snap.edges(), "ordering is not stable across calls"
    assert all(a < b for a, b in edges), "edges are not normalised low-index-first"
    assert len(edges) == len(set(edges)), "an edge appears twice"


def test_boundary_edges_find_the_open_side() -> None:
    snap = MeshSnapshot(
        object_id="o",
        vertices=[Vec3(), Vec3(1, 0, 0), Vec3(0, 1, 0)],
        triangles=[(0, 1, 2)],
    )
    assert len(snap.boundary_edges()) == 3


def test_epsilon_scales_away_from_the_origin() -> None:
    """float32 ULP at 500 m is already a third of the fixed epsilon, so points the server
    treats as coincident can round apart on the wire and crack the live view."""
    assert epsilon_at(10.0) == epsilon_at(0.0)
    assert epsilon_at(1000.0) > epsilon_at(10.0)


# ------------------------------------------------------------------ measurement

def test_every_defect_class_has_a_default_severity() -> None:
    """Without one table, identical defects get different severities depending on which
    code path produced them."""
    missing = [c for c in DefectClass if c not in DEFAULT_SEVERITY]
    assert missing == []


def test_unmeasurable_magnitude_is_distinct_from_zero() -> None:
    """Penetration depth between non-convex meshes is unsolved — libraries return zero on
    genuine contact. Rendering that as "no magnitude" hides a real defect."""
    d = Defect.of(
        DefectClass.PART_CLIPPING, "post_1", "contact confirmed, depth not computable",
        other_object_id="deck_1",
    )
    assert d.magnitude is None
    assert "not measurable" in d.describe()

    measured = Defect.of(DefectClass.PART_CLIPPING, "post_2", "overlap", magnitude=0.0)
    assert "0" in measured.describe()


def test_defect_of_applies_the_default_severity() -> None:
    assert Defect.of(DefectClass.NON_MANIFOLD_EDGE, "o", "x").severity is Severity.BLOCKER
    assert Defect.of(DefectClass.PART_CLIPPING, "o", "x").severity is Severity.WARNING


def test_report_cannot_claim_a_scope_it_did_not_examine() -> None:
    """This is the one property the scope field exists to provide."""
    stray = Defect.of(DefectClass.PART_CLIPPING, "wall_9999", "clips post_42")
    with pytest.raises(ValueError, match="scope"):
        MeasurementReport(defects=(stray,), scope=("wall_1", "wall_2"))


def test_report_accepts_findings_inside_its_declared_scope() -> None:
    d = Defect.of(DefectClass.PART_CLIPPING, "wall_1", "clips", other_object_id="wall_2")
    report = MeasurementReport(defects=(d,), scope=("wall_1", "wall_2"))
    assert not report.is_clean


def test_full_scene_report_needs_no_scope_list() -> None:
    d = Defect.of(DefectClass.FLIPPED_NORMAL, "anything", "x")
    assert MeasurementReport(defects=(d,), full_scene=True).blockers == ()


def test_pairwise_measurement_subject_is_split_on_the_pipe() -> None:
    m = Measurement(kind=MetricKind.DISTANCE, value=0.5, unit="m", subject="a|b")
    MeasurementReport(measurements=(m,), scope=("a", "b"))


def test_acceptance_query_comparing_without_an_expected_value_is_rejected() -> None:
    """`actual >= None` raises TypeError deep in an evaluator instead of failing cleanly."""
    from contracts import AcceptanceQuery

    with pytest.raises(ValueError, match="no expected value"):
        AcceptanceQuery(
            query_id="q", description="rail height", metric=MetricKind.DIMENSIONS,
            subject="rail", comparison=Comparison.GTE,
        )


def test_acceptance_query_that_cannot_fail_is_rejected() -> None:
    from contracts import AcceptanceQuery

    with pytest.raises(ValueError, match="checks nothing"):
        AcceptanceQuery(query_id="q", description="vibes", comparison=Comparison.NONE)


def test_tolerance_reconciles_to_the_loosest() -> None:
    """A check tighter than the rule it verifies fails geometry the rule permits — the
    same reading passing as intended joinery while failing its own acceptance query."""
    assert reconcile_tolerance(1e-4, 1e-3) == pytest.approx(1e-3)


# ------------------------------------------------------------------- operations

def test_mutating_tool_cannot_be_given_to_the_inspect_role() -> None:
    """Many inspect agents run concurrently precisely because none of their tools mutate."""
    with pytest.raises(ValueError, match="INSPECT"):
        ToolSpec(
            name="quick_fix", description="", roles=(ToolRole.INSPECT,),
            input_schema={}, mutating=True,
        )


def test_tool_visible_to_no_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="no role"):
        ToolSpec(name="orphan", description="", roles=(), input_schema={}, mutating=False)


def test_proposal_converts_to_an_operation_without_losing_its_targets() -> None:
    """Conflict detection compares target_objects; an operation that drops them cannot be
    checked against a concurrent one."""
    p = Proposal(
        proposal_id="p1", author="inspect-a", target_objects=("wall_3",),
        operation_kind="align_face", params={"axis": "z"},
        rationale="wall is 2 degrees off plumb",
    )
    op = p.to_operation(op_id="op-9", phase=Phase.REFINE)
    assert op.target_objects == ("wall_3",)
    assert op.proposal_id == "p1"
    assert op.kind == "align_face"


def test_operation_can_carry_an_asset_class_for_budget_checks() -> None:
    op = Operation(op_id="o1", kind="add_prop", asset_class=AssetClass.BACKGROUND_PROP)
    assert profile_for("roblox").budgets[op.asset_class] > 0


# ----------------------------------------------------------------- scene document

def test_head_cannot_go_negative() -> None:
    """A negative head slices from the end and silently drops the last operation instead
    of raising — an undo that produces a plausible wrong scene."""
    doc = SceneDocument()
    doc.append(Operation(op_id="a", kind="x"))
    with pytest.raises(ValueError, match="outside"):
        doc.set_head(-1)


def test_head_cannot_exceed_the_log() -> None:
    doc = SceneDocument()
    with pytest.raises(ValueError, match="outside"):
        doc.set_head(3)


def test_duplicate_operation_id_is_rejected() -> None:
    """Ids key the geometry cache, so a duplicate silently overwrites an earlier result."""
    doc = SceneDocument()
    doc.append(Operation(op_id="op-42", kind="add_cube"))
    with pytest.raises(ValueError, match="already in the log"):
        doc.append(Operation(op_id="op-42", kind="add_railing"))


def test_appending_after_an_undo_truncates_the_undone_tail() -> None:
    """Otherwise a later redo replays stale work ahead of the new operation, corrupting
    the exact ordering the replay model depends on."""
    doc = SceneDocument()
    for name in ("a", "b", "c"):
        doc.append(Operation(op_id=name, kind="x"))
    doc.set_head(1)

    doc.append(Operation(op_id="d", kind="x"))

    assert [o.op_id for o in doc.operations] == ["a", "d"]
    assert doc.head == 2


def test_opaque_operation_requires_a_snapshot_and_creates_a_barrier() -> None:
    """An opaque op with no barrier lets rollback attempt a replay across code it cannot
    replay, producing wrong geometry rather than an error."""
    doc = SceneDocument()
    with pytest.raises(ValueError, match="snapshot"):
        doc.append(Operation(op_id="raw1", kind="raw_exec", opaque=True))

    doc.append(Operation(op_id="raw1", kind="raw_exec", opaque=True), snapshot_path="/s/1.blend")
    barrier = doc.barrier_before(0)
    assert barrier is not None and barrier.op_id == "raw1"
    assert barrier.snapshot_path == "/s/1.blend"


def test_active_count_does_not_copy_the_log() -> None:
    """At tens of thousands of log entries, reaching for a count via the copying property
    turns every tool call into O(head) work."""
    doc = SceneDocument()
    for i in range(50):
        doc.append(Operation(op_id=f"op{i}", kind="x"))
    assert doc.active_count == 50 == len(doc.active_operations)


def test_checkpoints_are_named_and_unique() -> None:
    doc = SceneDocument()
    doc.append(Operation(op_id="a", kind="x"))
    doc.add_checkpoint("end-of-blockout")
    with pytest.raises(ValueError, match="already exists"):
        doc.add_checkpoint("end-of-blockout")
    assert doc.checkpoint("end-of-blockout").index == 1


def test_unknown_checkpoint_names_the_ones_that_exist() -> None:
    doc = SceneDocument()
    doc.add_checkpoint("start")
    with pytest.raises(KeyError, match="start"):
        doc.checkpoint("strat")


def test_scene_carries_its_own_cadence_setting() -> None:
    """A mid-run cadence change needs a typed home that survives, not a private key in a
    module's own state."""
    doc = SceneDocument()
    assert doc.check_cadence is CheckCadence.EVERY_GEOMETRY_CHANGE
    doc.check_cadence = CheckCadence.PHASE_BOUNDARIES
    assert doc.check_cadence is CheckCadence.PHASE_BOUNDARIES


# ------------------------------------------------------------------- write lock

def test_a_self_made_lease_is_not_the_lock() -> None:
    """Two agents each holding a WriteLease they constructed themselves is not a lock; it
    is two agents with the same dataclass."""
    doc = SceneDocument()
    doc.active_lease = WriteLease(
        holder="writer-a", phase=Phase.BLOCKOUT, lease_id="L1",
        granted_at_op=0, expires_at_op=64,
    )
    forged = WriteLease(
        holder="writer-b", phase=Phase.BLOCKOUT, lease_id="L2",
        granted_at_op=0, expires_at_op=64,
    )

    with pytest.raises(LockContention) as exc:
        doc.require_lease(forged)
    assert exc.value.holder == "writer-a"


def test_mutating_with_no_lease_at_all_is_contention_not_success() -> None:
    doc = SceneDocument()
    lease = WriteLease(
        holder="w", phase=Phase.BLOCKOUT, lease_id="L1", granted_at_op=0, expires_at_op=64
    )
    with pytest.raises(LockContention):
        doc.require_lease(lease)


def test_a_lease_expires_so_a_dead_agent_cannot_wedge_the_run() -> None:
    lease = WriteLease(
        holder="w", phase=Phase.BLOCKOUT, lease_id="L1", granted_at_op=0, expires_at_op=10
    )
    assert not lease.is_stale(9)
    assert lease.is_stale(10)


# -------------------------------------------------------------------- conflicts

def test_a_conflict_needs_at_least_two_proposals() -> None:
    with pytest.raises(ValueError, match="at least two"):
        Conflict(conflict_id="c1", proposals=(), overlapping_objects=("w",), detail="ghost")


def test_a_conflict_must_name_the_geometry_involved() -> None:
    p1 = Proposal(proposal_id="p1", author="a", target_objects=("w",), operation_kind="k")
    p2 = Proposal(proposal_id="p2", author="b", target_objects=("w",), operation_kind="k")
    with pytest.raises(ValueError, match="no objects"):
        Conflict(conflict_id="c1", proposals=(p1, p2), overlapping_objects=(), detail="x")


def test_conflict_describes_itself_with_a_location() -> None:
    p1 = Proposal(proposal_id="p1", author="inspect-a", target_objects=("w",), operation_kind="k")
    p2 = Proposal(proposal_id="p2", author="inspect-b", target_objects=("w",), operation_kind="k")
    c = Conflict(
        conflict_id="c1", proposals=(p1, p2), overlapping_objects=("wall_3",),
        detail="both move the same wall", location=Vec3(1, 2, 3), magnitude=0.04,
    )
    text = c.describe()
    assert "inspect-a" in text and "wall_3" in text and "0.04" in text


# ------------------------------------------------------------------ constraints

def test_anchors_are_symbolic_not_resolved_coordinates() -> None:
    """A symbolic anchor survives the target moving; a coordinate does not. This is the
    whole mechanism behind live re-solve."""
    a = Anchor(kind=AnchorKind.EDGE, object_id="stair_01", feature="outer_edge")
    assert a.key() == "edge:stair_01:outer_edge"


def test_constraint_set_reports_what_it_depends_on() -> None:
    from contracts import ConstraintSet

    cs = ConstraintSet(
        object_id="rail",
        constraints=(
            Constraint(
                kind=ConstraintKind.FOLLOWS,
                target=Anchor(kind=AnchorKind.EDGE, object_id="stair_01", feature="outer"),
            ),
        ),
    )
    assert cs.depends_on() == frozenset({"stair_01"})
    assert not cs.uses_escape_hatch


def test_raw_coordinate_use_is_visible_not_silent() -> None:
    """Agents reach for the easy path under pressure; this is how that becomes measurable
    instead of invisible."""
    from contracts import ConstraintSet

    cs = ConstraintSet(object_id="odd", raw_position=Vec3(2.34, 0, 1.87))
    assert cs.uses_escape_hatch


# ------------------------------------------------------------------------- wire

def test_rollback_takes_exactly_one_target() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        RollbackTarget()
    with pytest.raises(ValueError, match="exactly one"):
        RollbackTarget(steps=3, checkpoint="end-of-blockout")
    assert RollbackTarget(steps=5).steps == 5


def test_rollback_of_zero_steps_is_rejected() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        RollbackTarget(steps=0)


def test_an_empty_redirect_is_rejected() -> None:
    with pytest.raises(ValueError, match="silently dropped"):
        RedirectPayload(text="   ")


def test_cadence_payload_is_typed_not_a_loose_string() -> None:
    """frontend and viewer are built in parallel against this file alone — an untyped key
    name disagreement surfaces only at live WebSocket runtime."""
    assert CadencePayload(cadence=CheckCadence.PHASE_BOUNDARIES).cadence.value == "phase_boundaries"


# ---------------------------------------------------------------------- reports

def test_action_report_carries_operator_notes_back_to_the_agent() -> None:
    """MCP is call/response — a server cannot push into a connected agent's context. A
    redirect typed in the browser has exactly one way out: the next tool response."""
    from contracts import ActionReport

    r = ActionReport(
        op_id="op1", ok=True, summary="added railing",
        operator_notes=("make the railing simpler",),
    )
    assert "make the railing simpler" in r.render()


def test_skipped_checks_are_never_rendered_as_a_clean_result() -> None:
    from contracts import ActionReport

    r = ActionReport(op_id="op1", ok=True, summary="added railing", checks_skipped=True)
    assert "not a clean result" in r.render()


def test_export_report_banner_states_what_is_wrong() -> None:
    from contracts import ExportReport

    r = ExportReport(
        path="out.glb", profile="roblox", ok=True, triangle_count=12_000,
        defects=(Defect.of(DefectClass.NON_MANIFOLD_EDGE, "wall_1", "3 edges with 3+ faces"),),
        budget=10_000, over_budget_by=2_000,
    )
    banner = r.banner
    assert "non_manifold_edge" in banner
    assert "2000 over" in banner.replace(",", "")


def test_clean_export_says_so_plainly() -> None:
    from contracts import ExportReport

    r = ExportReport(path="out.glb", profile="godot", ok=True, triangle_count=900)
    assert "clean" in r.banner


# ------------------------------------------------------------------- transforms

def test_unapplied_scale_is_detectable() -> None:
    """It looks correct in a viewport and silently corrupts bevel width, booleans and
    physics — the only way to catch it is to measure."""
    assert Transform(scale=Vec3(3, 1, 1)).has_unapplied_scale()
    assert not Transform().has_unapplied_scale()


def test_roblox_profile_converts_metres_to_studs() -> None:
    p = profile_for("roblox")
    assert p.to_target_units(2.8) == pytest.approx(10.0)
    assert p.from_target_units(10.0) == pytest.approx(2.8)


def test_unknown_export_profile_lists_the_known_ones() -> None:
    with pytest.raises(KeyError, match="roblox"):
        profile_for("cryengine")


# --------------------------------------------------------------- platform reality

def test_every_report_string_survives_a_windows_console() -> None:
    """cp1252 is the default console encoding on the primary target platform, and it cannot
    encode an em dash or a set-intersection sign. These strings go to agent tool responses,
    to log files, and to a terminal — one unencodable character raises UnicodeEncodeError
    and takes down whatever was reporting, which on a clipping defect is the exact moment
    the tool is doing its most valuable work."""
    from contracts import ActionReport, ExportReport

    defect = Defect.of(
        DefectClass.PART_CLIPPING, "post_01", "interpenetrates the tread",
        other_object_id="tread_04", magnitude=0.03,
        suggestion="declare a JoineryIntent or move the post",
    )
    report = ActionReport(
        op_id="op-1", ok=False, summary="added railing",
        new_problems=(defect,), error_rule="ops.bad_dimension",
        error_detail="baluster_gap is -1", error_suggestion="pass a positive value",
        operator_notes=("make it simpler",),
    )
    export_report = ExportReport(
        path="out.glb", profile="roblox", ok=True, triangle_count=12_000,
        defects=(defect,), budget=10_000, over_budget_by=2_000,
    )

    for text in (defect.describe(), report.render(), export_report.banner):
        text.encode("cp1252")  # raises UnicodeEncodeError if this would crash on Windows
