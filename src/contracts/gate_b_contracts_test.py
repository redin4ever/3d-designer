"""Regression tests for the Gate B contract reconciliation (pass 2).

A separate file from ``contracts_test.py`` on purpose: that file is already 530 lines
against a 450-line test budget, and these tests share a single origin — every one is named
after a failure Phase 6 found by running the product, and cites the Gate B decision that
answered it. Splitting on "which pass added it" would be a bad seam; splitting on "which
review found it" is a real one.

Every test here failed before the corresponding contract change existed. Rule 4.
"""

from __future__ import annotations

import inspect

import pytest

from contracts import (
    ALWAYS_LEGAL_ROLES,
    DETAIL_THRESHOLD,
    MIN_READABLE_SCHEMA,
    PHASE_ORDER,
    SCHEMA_VERSION,
    AcceptanceResult,
    ActionReport,
    EngineError,
    LockContention,
    MetricKind,
    OperationResult,
    Phase,
    PhasePromotion,
    PhaseViolation,
    ProposalConflict,
    RuleError,
    RunPaused,
    ScenePort,
    ToolError,
    ToolRole,
    WriteLease,
    roles_for_phase,
)


# --------------------------------------------------------------- one error shape


def test_every_named_failure_shares_one_error_shape():
    """If the named exceptions do not share a base, the boundary in ``app/handlers.py``
    cannot tell "this failure names a rule" from "this one does not" with a single check —
    which is how Gate A 4.2 came to be half-kept, with validation errors naming a rule and
    geometry errors arriving as raw Python tracebacks. Gate B 5.4."""
    for exc in (
        EngineError(rule="engine.x", detail="d"),
        ToolError(rule="mcp.x", detail="d"),
        LockContention(holder="other", expires_at_op=9),
        RunPaused(),
        ProposalConflict(proposal_ids=("p1", "p2"), detail="overlap"),
    ):
        assert isinstance(exc, RuleError), type(exc)
        assert exc.rule and exc.detail
        assert set(exc.as_dict()) == {"rule", "detail", "suggestion"}


def test_rule_error_is_still_a_runtime_error():
    """``EngineError`` and ``LockContention`` were ``RuntimeError`` before this base was
    introduced beneath them. Any existing ``except RuntimeError`` must keep catching them,
    or introducing the base silently changes control flow across sixteen modules."""
    assert issubclass(RuleError, RuntimeError)
    assert isinstance(EngineError(rule="r", detail="d"), RuntimeError)


def test_lock_contention_still_names_its_holder_and_expiry():
    """Rewriting it onto the shared base must not lose the two fields that let a waiting
    agent wait usefully instead of retrying immediately, forever."""
    exc = LockContention(holder="agent-2", expires_at_op=41)
    assert exc.holder == "agent-2" and exc.expires_at_op == 41
    assert "agent-2" in exc.detail and "41" in exc.detail


# ------------------------------------------------------- role bound to the lease


def test_a_lease_only_permits_roles_legal_in_its_phase():
    """Before ADR-013 the role came from the string the caller passed with each call, so an
    agent could claim any role and a POLISH tool ran during blockout. If a lease permits a
    role its phase does not allow, that hole is open again."""
    lease = WriteLease(
        holder="a",
        phase=Phase.BLOCKOUT,
        lease_id="L1",
        granted_at_op=0,
        expires_at_op=64,
        roles=(ToolRole.BLOCKOUT, ToolRole.POLISH),
    )
    assert lease.permits((ToolRole.BLOCKOUT,))
    assert not lease.permits((ToolRole.POLISH,))
    assert ToolRole.POLISH not in lease.granted_roles()


def test_an_empty_role_grant_means_every_role_the_phase_allows():
    """A single-agent session should not have to enumerate roles. Empty must mean "all
    legal here" rather than "none", or every existing caller silently loses every tool."""
    lease = WriteLease(
        holder="a", phase=Phase.REFINE, lease_id="L", granted_at_op=0, expires_at_op=9
    )
    assert set(lease.granted_roles()) == set(roles_for_phase(Phase.REFINE))
    assert lease.permits((ToolRole.REFINE,))


def test_repair_and_align_stay_legal_in_every_phase_after_refine():
    """ADR-012 removed the promotion override, so a detail-phase operation that introduces
    a non-manifold edge must be fixable without going backwards. If repair is illegal in
    detail or polish, that phase can never pass its own acceptance query and can never be
    left — a deadlock with nobody watching."""
    for phase in (Phase.REFINE, Phase.DETAIL, Phase.POLISH):
        legal = roles_for_phase(phase)
        assert ToolRole.REPAIR in legal, phase
        assert ToolRole.ALIGN in legal, phase


def test_inspect_and_admin_are_legal_in_every_phase():
    """Read-only work cannot corrupt an ordering, and ADMIN owns checkpoints, rollback and
    raw execution — the tools an agent needs precisely when it is stuck."""
    for phase in PHASE_ORDER:
        legal = roles_for_phase(phase)
        for role in ALWAYS_LEGAL_ROLES:
            assert role in legal, (phase, role)


def test_detail_and_polish_tools_are_refused_during_blockout():
    """The exact ordering Phase 6 found unenforced: ``unwrap_uvs`` (POLISH) and
    ``add_railing`` (REFINE) both succeeded while the session had never left blockout."""
    legal = roles_for_phase(Phase.BLOCKOUT)
    assert ToolRole.DETAIL not in legal
    assert ToolRole.POLISH not in legal
    assert ToolRole.REFINE not in legal


def test_export_is_only_legal_in_polish():
    """Exporting a blockout is exporting boxes. Gate A 1.2 set the bar at "drops into a
    game engine", which is a polish-phase claim."""
    assert ToolRole.EXPORT in roles_for_phase(Phase.POLISH)
    for phase in (Phase.BLOCKOUT, Phase.REFINE, Phase.DETAIL):
        assert ToolRole.EXPORT not in roles_for_phase(phase), phase


def test_a_phase_violation_names_the_phase_the_role_and_the_way_forward():
    """With no promotion override, an agent that cannot work out how to move forward has
    no escape. A refusal saying only "not allowed" makes it retry the same call forever —
    the failure Gate A 4.2 was asked about."""
    exc = PhaseViolation(
        tool="unwrap_uvs",
        held=(ToolRole.BLOCKOUT,),
        phase=Phase.BLOCKOUT,
        required=(ToolRole.POLISH,),
    )
    assert exc.rule == "orchestration.phase_violation"
    assert "unwrap_uvs" in exc.detail
    assert "blockout" in exc.detail
    assert "polish" in exc.detail
    assert "promote_phase" in exc.suggestion


# ------------------------------------------------- promotion is a real gate now


def test_a_promotion_must_declare_something_to_check():
    """ADR-012 removed the override, so a promotion with no queries cannot be refused —
    which is precisely the placeholder behaviour ("did anything happen at all") it
    replaced."""
    with pytest.raises(ValueError, match="no acceptance queries"):
        PhasePromotion(from_phase=Phase.BLOCKOUT, to_phase=Phase.REFINE, queries=())


def test_phase_promotion_no_longer_carries_an_override_flag():
    """Leaving the field in place would let a caller keep passing ``allow_override=True``
    and believe it did something."""
    assert "allow_override" not in getattr(PhasePromotion, "__annotations__", {})


def test_an_acceptance_failure_says_what_to_do_about_it():
    """The only thing standing between an unattended agent and a phase it cannot leave."""
    r = AcceptanceResult(
        query_id="no_holes",
        passed=False,
        actual=3.0,
        expected=0.0,
        subject="wall_n",
        reason="3 boundary holes",
        suggested_operation="fill_boundary_holes(object_id='wall_n')",
    )
    text = r.describe()
    assert "FAIL" in text
    assert "wall_n" in text
    assert "fill_boundary_holes" in text


def test_a_passing_acceptance_result_stays_terse():
    """Token efficiency has a measured cost/accuracy tradeoff, and most results pass."""
    assert AcceptanceResult(query_id="q", passed=True).describe() == "PASS q"


# ----------------------------------------------------------- realism metrics


def test_realism_metrics_have_their_own_metric_kinds():
    """``detail`` and ``uv`` shipped reusing ANGLE/DISTANCE/GAP_WIDTH with the real name
    buried in ``Measurement.detail``, so nothing could filter or threshold on them — and
    Gate B 3.4 makes bevel topology quality a deliverable that must be expressible as an
    acceptance query. Filed twice as a contract request and deferred twice."""
    assert MetricKind.TRIANGLE_ASPECT_RATIO.value == "triangle_aspect_ratio"
    assert MetricKind.SHARP_EDGE_RATIO.value == "sharp_edge_ratio"
    assert MetricKind.EDGE_LENGTH_UNIFORMITY.value == "edge_length_uniformity"


# ------------------------------------------- assumptions and summarised reports


def test_an_operation_result_can_report_what_it_assumed():
    """Gate A 6.4 chose that the tool never carries real-world dimensions; ``add_railing``
    defaulted three cross-sections to 5cm/5cm/3cm invisibly. Gate B 1.4 kept the defaults
    and required them reported, so an agent can see and correct them."""
    r = OperationResult(
        op_id="op1", ok=True, assumptions=("post_size defaulted to 0.05 x 0.05 m",)
    )
    assert r.assumptions


def test_a_summarised_report_says_that_it_summarised():
    """A report that drops per-object detail without saying so reads as a complete one —
    the same failure ``checks_skipped`` exists to prevent. Gate B 4.3."""
    r = ActionReport(
        op_id="op1",
        ok=True,
        summary="railing",
        changed=tuple(f"o{i}" for i in range(40)),
        breakdown=(("post", 5), ("baluster", 34), ("top_rail", 1)),
        detail_omitted=40,
        detail_hint="call describe_object(<id>)",
        total_triangles=604,
    )
    text = r.render()
    assert "5x post" in text
    assert "604 tris" in text
    assert "40 object(s)" in text
    assert "describe_object" in text


def test_a_report_that_omitted_nothing_says_nothing_about_omission():
    """Noise on every small call would cost more tokens than the summarisation saves."""
    r = ActionReport(op_id="op1", ok=True, summary="a floor", changed=("floor",))
    assert "omitted" not in r.render()


def test_assumptions_reach_the_agent_in_the_rendered_report():
    """A field nothing renders is a field the agent never sees."""
    r = ActionReport(
        op_id="op1", ok=True, summary="railing",
        assumptions=("post_size defaulted to 0.05 x 0.05 m",),
    )
    assert "ASSUMED" in r.render()
    assert "0.05" in r.render()


def test_the_detail_threshold_is_a_named_constant_not_a_magic_number():
    """Two modules have to agree on it — the reporter that summarises and the tool that
    serves the omitted detail."""
    assert isinstance(DETAIL_THRESHOLD, int)
    assert DETAIL_THRESHOLD > 0


# ------------------------------------------------------------ persistence v2


def test_the_schema_version_moved_and_still_declares_what_it_can_read():
    """v1 dropped every constraint silently. Reading a v1 file without saying so would
    reproduce that bug one layer up, as a scene that looks intact and has quietly lost the
    reason for its geometry. ADR-015."""
    assert SCHEMA_VERSION == 2
    assert MIN_READABLE_SCHEMA == 1
    assert MIN_READABLE_SCHEMA < SCHEMA_VERSION


# -------------------------------------------------------- ScenePort, at last


def test_scene_port_is_declared_once_in_the_frozen_surface():
    """Declared locally in ``orchestration`` it was wrong twice, each time producing a P0
    that three green suites could not see because both doubles matched the declaration
    rather than the real ``Scene``: ``document`` was a method where ``Scene`` has a
    property, and ``apply`` omitted ``lease`` so every mutating call failed."""
    assert isinstance(ScenePort.document, property)
    assert isinstance(ScenePort.engine, property)
    params = inspect.signature(ScenePort.apply).parameters
    assert "lease" in params
    assert "snapshot_path" in params
