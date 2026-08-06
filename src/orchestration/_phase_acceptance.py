"""What "this phase is done" means, per phase, as re-runnable measurements (ADR-012).

``can_promote`` used to compute ``passed = len(produced_this_phase) > 0`` — "did anything
happen at all" — while ``measure.evaluate`` had zero non-test call sites anywhere in the
product. This module is what that placeholder was standing in for.

**Every set below must be satisfiable.** With the override removed at Gate B 1.1, a query
that cannot be passed is not a strict check; it is a phase an unattended run can never leave,
with nobody to redirect it. So the sets are cumulative and deliberately modest — blockout
does not demand UVs, refine does not demand bevels, and each phase asks only for what its own
name promises:

| Phase | Adds |
|---|---|
| blockout | some geometry exists; every object manifold; no unapplied transforms |
| refine   | no boundary holes; no undeclared clipping; no visual gaps over threshold |
| detail   | everything refine demands, still true after detailing |
| polish   | everything detail demands, plus UVs present and inside the polygon budget |

Two checks are evaluated here rather than by ``measure``: "the scene has geometry" is
scene-level and has no subject to measure, and "this object has UVs" has no
:class:`contracts.MetricKind` and no :class:`contracts.DefectClass` to express it. Both are
filed as contract requests; both produce the same :class:`contracts.AcceptanceResult` shape as
everything else, carrying subject, actual, expected and a concrete suggested operation, so a
caller cannot tell which evaluator produced a given failure and does not need to.
"""

from __future__ import annotations

from dataclasses import replace

from contracts import (
    DEFAULT_PROFILE,
    AcceptanceQuery,
    AcceptanceResult,
    AssetClass,
    Comparison,
    DefectClass,
    EngineProtocol,
    JoineryIntent,
    MetricKind,
    Phase,
    profile_for,
)

from . import _suggested_fix as fix

__all__ = ["evaluate_phase", "queries_for", "VISUAL_GAP_MAX", "POLYGON_BUDGET"]

VISUAL_GAP_MAX = 0.01
"""Metres. Two parts that should meet and are further apart than this are a defect.

Also the margin the pair search runs with: a gap check that only looks at pairs whose
bounding boxes already overlap can never find a gap, which is the shape of bug that leaves a
detector permanently returning nothing.
"""

POLYGON_BUDGET = profile_for(DEFAULT_PROFILE).budgets[AssetClass.STANDARD_PROP]
"""Read from the export profile table rather than written here, so the number a polish phase
is held to and the number the exporter warns against cannot drift apart."""

_MANIFOLD: tuple[DefectClass, ...] = (
    DefectClass.NON_MANIFOLD_EDGE,
    DefectClass.NON_MANIFOLD_VERTEX,
)


def _object_queries(phase: Phase, object_id: str) -> list[AcceptanceQuery]:
    queries = [
        AcceptanceQuery(
            query_id=f"{phase.value}.manifold.{object_id}",
            description=f"{object_id} has no non-manifold edges or vertices",
            forbidden_defects=_MANIFOLD,
            subject=object_id,
        ),
        AcceptanceQuery(
            query_id=f"{phase.value}.transforms_applied.{object_id}",
            description=f"{object_id} has no unapplied scale",
            forbidden_defects=(DefectClass.UNAPPLIED_TRANSFORM,),
            subject=object_id,
        ),
    ]
    if phase is Phase.BLOCKOUT:
        return queries
    queries.append(
        AcceptanceQuery(
            query_id=f"{phase.value}.watertight.{object_id}",
            description=f"{object_id} has no boundary holes",
            forbidden_defects=(DefectClass.BOUNDARY_HOLE,),
            subject=object_id,
        )
    )
    if phase is Phase.POLISH:
        queries.append(
            AcceptanceQuery(
                query_id=f"{phase.value}.budget.{object_id}",
                description=f"{object_id} is within the {DEFAULT_PROFILE} polygon budget",
                metric=MetricKind.TRIANGLE_COUNT,
                subject=object_id,
                expected=float(POLYGON_BUDGET),
                comparison=Comparison.LTE,
            )
        )
    return queries


def _pair_queries(
    phase: Phase, pair: tuple[str, str], joinery: tuple[JoineryIntent, ...]
) -> list[AcceptanceQuery]:
    a, b = pair
    subject = f"{a}|{b}"
    return [
        AcceptanceQuery(
            query_id=f"{phase.value}.no_clipping.{subject}",
            description=f"{a} and {b} do not interpenetrate without a declared joint",
            forbidden_defects=(DefectClass.PART_CLIPPING,),
            subject=subject,
            params={"joinery": joinery},
        ),
        AcceptanceQuery(
            query_id=f"{phase.value}.no_visual_gap.{subject}",
            description=f"{a} and {b} are not left {VISUAL_GAP_MAX}m short of meeting",
            forbidden_defects=(DefectClass.VISUAL_GAP,),
            subject=subject,
            tolerance=VISUAL_GAP_MAX,
            params={"max_gap": VISUAL_GAP_MAX},
        ),
    ]


def queries_for(
    phase: Phase,
    objects: tuple[str, ...],
    pairs: tuple[tuple[str, str], ...] = (),
    joinery: tuple[JoineryIntent, ...] = (),
) -> tuple[AcceptanceQuery, ...]:
    """Every ``measure``-evaluable query this phase demands, built against live object ids.

    Built per call rather than declared as a constant because the subjects *are* the scene:
    a query set that named objects up front could only ever check a scene somebody had
    already predicted.
    """
    queries: list[AcceptanceQuery] = []
    for object_id in objects:
        queries.extend(_object_queries(phase, object_id))
    if phase is not Phase.BLOCKOUT:
        for pair in pairs:
            queries.extend(_pair_queries(phase, pair, joinery))
    return tuple(queries)


def _enrich(query: AcceptanceQuery, result: AcceptanceResult) -> AcceptanceResult:
    """Give a failure the four things ADR-012 requires it to carry.

    ``measure.evaluate`` returns ``query_id``/``passed``/``actual``/``reason``/``defects`` —
    correct, and not enough on its own now that a refusal is all an unattended agent has. The
    query knows its subject and its threshold; ``_suggested_fix`` knows the call. For a
    forbidden-defect query there is no measured number, so the count of defects found against
    a threshold of zero is the honest pair.
    """
    if result.passed:
        return result
    actual, expected = result.actual, query.expected
    if query.comparison is Comparison.NONE:
        actual, expected = float(len(result.defects)), 0.0
    return replace(
        result,
        subject=query.subject or "(scene)",
        actual=actual,
        expected=expected,
        suggested_operation=fix.for_query(query, result.defects),
    )


def _scene_has_geometry(phase: Phase, objects: tuple[str, ...]) -> AcceptanceResult:
    """Evaluated here, not by ``measure``: it has no subject to measure against."""
    return AcceptanceResult(
        query_id=f"{phase.value}.scene_has_geometry",
        passed=bool(objects),
        actual=float(len(objects)),
        expected=1.0,
        subject="(scene)",
        reason="" if objects else "the scene contains no objects at all",
        suggested_operation="" if objects else fix.ADD_FIRST_OBJECT,
    )


def _uvs_present(engine: EngineProtocol, object_id: str) -> AcceptanceResult:
    """Evaluated here, not by ``measure``: there is no UV ``MetricKind`` and no
    "missing UVs" ``DefectClass`` to express this as a query ``measure`` could run."""
    try:
        has_uvs = engine.snapshot(object_id).uvs is not None
    except Exception:  # noqa: BLE001 — a vanished id must not crash the gate
        has_uvs = False
    return AcceptanceResult(
        query_id=f"polish.uvs.{object_id}",
        passed=has_uvs,
        actual=1.0 if has_uvs else 0.0,
        expected=1.0,
        subject=object_id,
        reason="" if has_uvs else f"{object_id} carries no UV layer, so it cannot be baked",
        suggested_operation="" if has_uvs else fix.unwrap_call(object_id),
    )


def evaluate_phase(
    engine: EngineProtocol,
    phase: Phase,
    objects: tuple[str, ...],
    pairs: tuple[tuple[str, str], ...] = (),
    joinery: tuple[JoineryIntent, ...] = (),
) -> tuple[AcceptanceResult, ...]:
    """Run every query this phase demands against live geometry, right now.

    Never raises. A detector that blows up on one object must not take the whole gate with
    it — an exception here would be indistinguishable from "cannot promote" to the caller
    while being a completely different problem, and ADR-012 leaves no override to escape a
    gate that is broken rather than merely failing.
    """
    import measure

    results: list[AcceptanceResult] = [_scene_has_geometry(phase, objects)]
    for query in queries_for(phase, objects, pairs, joinery):
        try:
            results.append(_enrich(query, measure.evaluate(engine, query)))
        except Exception as exc:  # noqa: BLE001
            results.append(
                AcceptanceResult(
                    query_id=query.query_id,
                    passed=False,
                    actual=None,
                    expected=query.expected,
                    subject=query.subject or "(scene)",
                    reason=f"the check itself failed: {exc!r}",
                    suggested_operation=fix.for_query(query, ()),
                )
            )
    if phase is Phase.POLISH:
        results.extend(_uvs_present(engine, object_id) for object_id in objects)
    return tuple(results)
