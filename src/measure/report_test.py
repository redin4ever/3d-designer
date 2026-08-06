"""Tests for the composition layer: inspect, report, evaluate, is_watertight, and purity.

``report()`` and ``evaluate()`` are the two functions the rest of the system actually calls
— Gate A 4.1's "new problems" field and ADR-005's "definition-of-done is a re-run
measurement, not a claim" both resolve to a call here. If either lies, every downstream
consumer (orchestration, export, phase promotion) inherits the lie.
"""

from __future__ import annotations

import pytest

from contracts import (
    AcceptanceQuery,
    Comparison,
    DefectClass,
    MetricKind,
    Severity,
    Transform,
    Vec3,
)
from measure import (
    bounds,
    dimensions,
    distance,
    evaluate,
    find_boundary_holes,
    find_clipping,
    find_unapplied_transforms,
    gap_width,
    inspect,
    is_watertight,
    report,
    triangle_count,
    volume,
)
from testing import unit_cube

# --------------------------------------------------------------------------- inspect


def test_inspect_is_empty_over_a_clean_box(engine) -> None:
    """A false positive from the composed check would report a broken object as broken when
    it is not, and an agent has no way to tell that apart from a genuine defect."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    assert inspect(engine, "box") == ()


def test_inspect_finds_the_hole_a_single_finder_would_find(engine) -> None:
    """``inspect()`` composes the single-object checks; if it drops one silently, an agent
    calling the composed function instead of the individual finder gets a clean bill of
    health that is wrong."""
    verts, faces = unit_cube()
    engine.create_mesh("open", verts, faces[:-1])

    result = inspect(engine, "open")

    assert any(d.defect_class is DefectClass.BOUNDARY_HOLE for d in result)


def test_inspect_finds_self_intersections_not_just_boundary_holes(engine) -> None:
    """The only composition test above uses a boundary hole; an inspect() that composes
    six of the seven single-object checks and silently forgets find_self_intersections
    would still pass it, while dropping the one check that is a BLOCKER on import into an
    engine or a slicer and is invisible to a render-based review either way."""
    verts = [
        Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(0, 4, 0),
        Vec3(1, 1, -2), Vec3(1, 1, 2), Vec3(3, 1, 0),
    ]
    faces = [(0, 1, 2), (3, 4, 5)]
    engine.create_mesh("cross", verts, faces)

    result = inspect(engine, "cross")

    assert any(d.defect_class is DefectClass.SELF_INTERSECTION for d in result)


# ----------------------------------------------------------------------- is_watertight


def test_closed_box_is_watertight(engine) -> None:
    """A false negative here would let a genuinely closed mesh be reported as leaking,
    which is the exact signal a slicer or game engine import check relies on."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    assert is_watertight(engine, "box") is True


def test_box_missing_a_face_is_not_watertight(engine) -> None:
    """A false positive here is the dangerous direction: it tells an agent a leaking mesh
    is safe to export, and the failure only surfaces later, in the slicer or game engine."""
    verts, faces = unit_cube()
    engine.create_mesh("open", verts, faces[:-1])

    assert is_watertight(engine, "open") is False


def test_non_manifold_edge_makes_an_object_not_watertight(engine) -> None:
    """Both existing is_watertight tests are decided purely by boundary holes; a version
    that checks only find_boundary_holes and ignores find_non_manifold_edges would pass
    both and still tell an agent a mesh is safe to export when it will fail on import into
    an engine or a slicer — non-manifold edges are a BLOCKER for exactly that reason."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, -1, 0), Vec3(0, 0, 1)]
    faces = [(0, 1, 2), (0, 1, 3), (0, 1, 4)]
    engine.create_mesh("fan", verts, faces)

    assert is_watertight(engine, "fan") is False


# ------------------------------------------------------------------------------ report


def test_report_is_clean_over_a_clean_scene(engine) -> None:
    """A report that manufactures phantom defects over genuinely clean geometry teaches an
    agent to distrust the exact tool ADR-005 says should be trusted over its own judgement."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    rpt = report(engine, scope=("box",))

    assert rpt.is_clean
    assert rpt.blockers == ()


def test_report_separates_blockers_from_warnings_by_the_default_table(engine) -> None:
    """The same three non-manifold edges must not read as blockers from one code path and
    warnings from another — ``DEFAULT_SEVERITY`` exists precisely so identical defects
    cannot end up differently classified depending on which code path produced them."""
    verts, faces = unit_cube()
    hole_id = engine.create_mesh("hole_box", verts, faces[:-1])
    engine.create_primitive("warn_box", "cube", Vec3(1, 1, 1))
    engine.set_transform("warn_box", Transform(scale=Vec3(3, 1, 1)))

    rpt = report(engine, scope=(hole_id, "warn_box"))

    assert any(d.defect_class is DefectClass.BOUNDARY_HOLE for d in rpt.defects)
    assert any(d.defect_class is DefectClass.UNAPPLIED_TRANSFORM for d in rpt.defects)
    assert all(d.severity is Severity.BLOCKER for d in rpt.blockers)
    assert not any(d.defect_class is DefectClass.UNAPPLIED_TRANSFORM for d in rpt.blockers)


def test_report_scope_covers_every_object_it_actually_examined(engine) -> None:
    """``MeasurementReport.__post_init__`` raises if the declared scope does not cover every
    object a defect touches (see ``contracts/contracts_test.py::
    test_report_cannot_claim_a_scope_it_did_not_examine``). ``report()`` must therefore
    widen its declared scope to cover objects it reached only through ``pairs`` — it cannot
    construct a valid report otherwise when a clipping check finds something outside the
    caller's declared list."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(0.5, 0, 0)))

    rpt = report(engine, scope=("a",), pairs=[("a", "b")])

    assert "a" in rpt.scope
    assert "b" in rpt.scope


def test_report_with_pairs_actually_runs_the_clipping_check(engine) -> None:
    """The scope test above only checks scope membership, never rpt.defects. An
    implementation that widens its declared scope textually to satisfy
    MeasurementReport's validation but never actually calls find_clipping would pass that
    test while reporting a clipping scene as clean — the exact silent-wrong-answer failure
    ADR-005 exists to prevent."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(0.5, 0, 0)))

    rpt = report(engine, scope=("a",), pairs=[("a", "b")])

    assert any(d.defect_class is DefectClass.PART_CLIPPING for d in rpt.defects)
    assert rpt.is_clean is False


# ---------------------------------------------------------------------------- evaluate


def test_evaluate_passing_query_returns_the_actual_value(engine) -> None:
    """A definition-of-done that reports pass/fail with no actual number gives the agent
    nothing to log or show the user as evidence the check genuinely ran against geometry."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    query = AcceptanceQuery(
        query_id="q-volume", description="unit cube volume", metric=MetricKind.VOLUME,
        subject="box", expected=1.0, tolerance=1e-2, comparison=Comparison.EQ,
    )

    result = evaluate(engine, query)

    assert result.passed is True
    assert result.actual == pytest.approx(1.0, rel=1e-2)


def test_evaluate_failing_query_returns_false_and_a_reason(engine) -> None:
    """A definition-of-done that fails silently is as bad as one that never ran — Gate A
    4.2 requires the agent be told which rule broke, never left to infer it from a bare
    ``False``."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    query = AcceptanceQuery(
        query_id="q-volume-wrong", description="wrong volume", metric=MetricKind.VOLUME,
        subject="box", expected=5.0, tolerance=1e-2, comparison=Comparison.EQ,
    )

    result = evaluate(engine, query)

    assert result.passed is False
    assert result.reason != ""


def test_evaluate_fails_when_a_forbidden_defect_is_present(engine) -> None:
    """This is the mechanism ADR-005 calls the definition of done for a "no clipping" task
    — it has to re-measure the live geometry, never trust that nobody complained."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(0.97, 0, 0)))
    query = AcceptanceQuery(
        query_id="q-no-clip", description="a and b must not clip",
        forbidden_defects=(DefectClass.PART_CLIPPING,), subject="a|b",
        comparison=Comparison.NONE,
    )

    result = evaluate(engine, query)

    assert result.passed is False


def test_evaluate_passes_when_the_forbidden_defect_is_absent(engine) -> None:
    """Without this, a broken ``evaluate()`` that always returns ``passed=False`` for a
    forbidden-defects query would pass the test above for the wrong reason."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(3.0, 0, 0)))
    query = AcceptanceQuery(
        query_id="q-no-clip-2", description="a and b must not clip",
        forbidden_defects=(DefectClass.PART_CLIPPING,), subject="a|b",
        comparison=Comparison.NONE,
    )

    result = evaluate(engine, query)

    assert result.passed is True


def test_evaluate_lte_comparison_passes_when_actual_is_under_expected(engine) -> None:
    """Budget-style "at most N" queries (Gate A 12.2's polygon budgets) are the main real
    use of Comparison.LTE; if it is never exercised, an implementation that only handles
    EQ, or that silently treats LTE as GTE, would ship undetected and every polygon-budget
    acceptance check would pass or fail for the wrong reason."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    actual_tris = engine.snapshot("box").triangle_count
    query = AcceptanceQuery(
        query_id="q-lte", description="triangle budget", metric=MetricKind.TRIANGLE_COUNT,
        subject="box", expected=float(actual_tris + 100), tolerance=1e-6,
        comparison=Comparison.LTE,
    )

    result = evaluate(engine, query)

    assert result.passed is True


def test_evaluate_gte_comparison_fails_when_actual_is_under_expected(engine) -> None:
    """The mirror image of LTE — a "must be at least N" floor (a minimum detail level or
    volume) is only meaningful if falling below the floor is actually detected rather than
    silently reported as passing by a comparison that is never exercised."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    query = AcceptanceQuery(
        query_id="q-gte", description="volume floor", metric=MetricKind.VOLUME,
        subject="box", expected=5.0, tolerance=1e-6, comparison=Comparison.GTE,
    )

    result = evaluate(engine, query)

    assert result.passed is False


def test_evaluate_pairwise_metric_resolves_the_subject_split_on_pipe(engine) -> None:
    """AcceptanceQuery.subject follows Measurement.subject's own "a|b" convention for a
    pairwise metric; an evaluate() that only knows how to look up a single-object subject
    would mis-resolve "a|b" as one unknown object id instead of a pair, breaking every
    acceptance query written against distance, angle, or gap_width."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive("b", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(1.5, 0, 0)))
    query = AcceptanceQuery(
        query_id="q-pairwise", description="a and b are 0.5m apart", metric=MetricKind.DISTANCE,
        subject="a|b", expected=0.5, tolerance=1e-3, comparison=Comparison.EQ,
    )

    result = evaluate(engine, query)

    assert result.passed is True
    assert result.actual == pytest.approx(0.5, abs=1e-3)


# ------------------------------------------------------------------------------ purity


def test_measure_never_mutates_the_engine(engine) -> None:
    """A measurement function that mutates would corrupt the model while claiming only to
    inspect it — this is the property that lets any number of read-only inspect agents run
    concurrently beside the single writer (ADR-007). If this fails, some function above the
    line called a mutating ``EngineProtocol`` method instead of only reading a snapshot."""
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_primitive(
        "b", "cube", Vec3(1, 1, 1),
        Transform(translation=Vec3(0.97, 0, 0), scale=Vec3(2, 1, 1)),
    )

    objects_before = engine.list_objects()
    snap_a_before = engine.snapshot("a")
    snap_b_before = engine.snapshot("b")
    calls_before = list(engine.calls)

    bounds(engine, "a")
    dimensions(engine, "a")
    distance(engine, "a", "b")
    gap_width(engine, "a", "b")
    volume(engine, "a")
    triangle_count(engine, "a")
    find_unapplied_transforms(engine, "b")
    find_boundary_holes(engine, "a")
    find_clipping(engine, [("a", "b")])
    inspect(engine, "a")
    report(engine, scope=("a", "b"), pairs=[("a", "b")])
    evaluate(
        engine,
        AcceptanceQuery(
            query_id="q-purity", description="purity probe", metric=MetricKind.VOLUME,
            subject="a", expected=1.0, tolerance=1.0, comparison=Comparison.EQ,
        ),
    )

    assert engine.list_objects() == objects_before
    assert engine.snapshot("a") == snap_a_before
    assert engine.snapshot("b") == snap_b_before
    assert engine.calls == calls_before
