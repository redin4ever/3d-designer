"""Composition: ``inspect``, ``report``, ``evaluate``, ``is_watertight``.

Combines the single-object checks (``topology``), the pairwise checks (``intersections``)
and the metric queries (``metrics``) into the shapes the rest of the system consumes: a
defect list, a scoped report, and a pass/fail acceptance result. ``evaluate`` is the
definition-of-done mechanism (ADR-005) — a re-run measurement, never an agent's claim.

Pure: read-only, composed entirely from the pure functions in the sibling files.
"""

from __future__ import annotations

from typing import Sequence

from contracts import (
    AcceptanceQuery,
    AcceptanceResult,
    Comparison,
    Defect,
    DefectClass,
    EngineProtocol,
    JoineryIntent,
    Measurement,
    MeasurementReport,
    MetricKind,
)

from .intersections import find_clipping, find_self_intersections, find_visual_gaps
from .metrics import (
    angle_between,
    bounds,
    dimensions,
    distance,
    gap_width,
    surface_angle,
    triangle_count,
    volume,
)
from .topology import (
    find_boundary_holes,
    find_flipped_normals,
    find_loose_or_duplicate,
    find_non_manifold_edges,
    find_non_manifold_vertices,
    find_unapplied_transforms,
)

__all__ = ["inspect", "report", "evaluate", "is_watertight"]

#: Single-object metrics: looked up by ``query.subject`` alone.
_SINGLE_METRICS = {
    MetricKind.BOUNDS: bounds,
    MetricKind.DIMENSIONS: dimensions,
    MetricKind.VOLUME: volume,
    MetricKind.TRIANGLE_COUNT: triangle_count,
}

#: Pairwise metrics: ``query.subject`` is ``"a|b"``, matching ``Measurement.subject``'s
#: own convention.
_PAIR_METRICS = {
    MetricKind.DISTANCE: distance,
    MetricKind.ANGLE: angle_between,
    MetricKind.SURFACE_ANGLE: surface_angle,
    MetricKind.GAP_WIDTH: gap_width,
}

#: Single-object defect finders, dispatched by class for ``evaluate``'s
#: ``forbidden_defects``. Pairwise classes (``PART_CLIPPING``, ``VISUAL_GAP``) are
#: handled separately below since they need two objects, not one.
_SINGLE_DEFECT_FINDERS = {
    DefectClass.BOUNDARY_HOLE: find_boundary_holes,
    DefectClass.NON_MANIFOLD_EDGE: find_non_manifold_edges,
    DefectClass.NON_MANIFOLD_VERTEX: find_non_manifold_vertices,
    DefectClass.LOOSE_OR_DUPLICATE: find_loose_or_duplicate,
    DefectClass.FLIPPED_NORMAL: find_flipped_normals,
    DefectClass.UNAPPLIED_TRANSFORM: find_unapplied_transforms,
    DefectClass.SELF_INTERSECTION: find_self_intersections,
}


def inspect(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """Every single-object check, concatenated: the six ``topology`` finders plus
    :func:`measure.find_self_intersections`. Excludes the pairwise checks
    (:func:`measure.find_clipping`, :func:`measure.find_visual_gaps`), which need a second
    object and cannot run from an object id alone.
    """
    return (
        find_boundary_holes(engine, object_id)
        + find_non_manifold_edges(engine, object_id)
        + find_non_manifold_vertices(engine, object_id)
        + find_loose_or_duplicate(engine, object_id)
        + find_flipped_normals(engine, object_id)
        + find_unapplied_transforms(engine, object_id)
        + find_self_intersections(engine, object_id)
    )


def report(
    engine: EngineProtocol,
    scope: Sequence[str],
    pairs: Sequence[tuple[str, str]] = (),
    joinery: Sequence[JoineryIntent] = (),
    full_scene: bool = False,
) -> MeasurementReport:
    """Run :func:`inspect` over every object in ``scope`` and :func:`measure.find_clipping`
    over ``pairs``, and assemble a :class:`MeasurementReport`.

    The report's declared ``scope`` must cover every object genuinely examined — including
    objects reached only through ``pairs`` — never merely the caller-supplied ``scope``
    sequence verbatim. ``MeasurementReport.__post_init__`` enforces this at construction: a
    report that names a scope narrower than what it actually looked at cannot be built at
    all, by design (ADR-011's "a report cannot claim a scope it did not examine").
    """
    defects: list[Defect] = []
    examined: set[str] = set(scope)

    for object_id in scope:
        defects.extend(inspect(engine, object_id))

    if pairs:
        defects.extend(find_clipping(engine, pairs, joinery))
        for a, b in pairs:
            examined.add(a)
            examined.add(b)

    return MeasurementReport(
        defects=tuple(defects), scope=tuple(sorted(examined)), full_scene=full_scene
    )


def _resolve_metric(engine: EngineProtocol, query: AcceptanceQuery) -> Measurement:
    if query.metric in _PAIR_METRICS:
        a, b = query.subject.split("|", 1)
        return _PAIR_METRICS[query.metric](engine, a, b)
    return _SINGLE_METRICS[query.metric](engine, query.subject)


def _compare(actual: float, expected: float, tolerance: float, comparison: Comparison) -> bool:
    if comparison is Comparison.EQ:
        return abs(actual - expected) <= tolerance
    if comparison is Comparison.LTE:
        return actual <= expected + tolerance
    if comparison is Comparison.GTE:
        return actual >= expected - tolerance
    raise ValueError(f"measure.evaluate: comparison {comparison!r} is not handled")


def _forbidden_defects_present(
    engine: EngineProtocol, query: AcceptanceQuery
) -> tuple[Defect, ...]:
    found: list[Defect] = []
    for defect_class in query.forbidden_defects:
        if defect_class in _SINGLE_DEFECT_FINDERS:
            found.extend(_SINGLE_DEFECT_FINDERS[defect_class](engine, query.subject))
        elif defect_class is DefectClass.PART_CLIPPING:
            a, b = query.subject.split("|", 1)
            joinery = query.params.get("joinery", ())
            found.extend(find_clipping(engine, [(a, b)], joinery))
        elif defect_class is DefectClass.VISUAL_GAP:
            a, b = query.subject.split("|", 1)
            max_gap = query.params.get("max_gap", query.tolerance)
            found.extend(find_visual_gaps(engine, [(a, b)], max_gap))
        # Any other class (e.g. BUDGET_EXCEEDED) has no finder owned by this module —
        # nothing in `measure` can answer it, so it contributes no findings here.
    return tuple(found)


def evaluate(engine: EngineProtocol, query: AcceptanceQuery) -> AcceptanceResult:
    """Re-run ``query`` against live geometry and return whether it passes.

    For a ``comparison`` other than ``Comparison.NONE``, compares the named ``metric`` on
    ``query.subject`` (split on ``"|"`` for a pairwise metric, matching
    :attr:`Measurement.subject`'s convention) against ``query.expected`` within
    ``query.tolerance``. For ``forbidden_defects``, runs the matching detector(s) against
    ``query.subject`` and fails if any forbidden class is found. On failure, ``reason`` is
    always populated — Gate A 4.2: an agent is told which rule broke, never left to infer it
    from a bare ``False``.
    """
    actual: float | None = None
    passed = True
    reasons: list[str] = []

    if query.comparison is not Comparison.NONE:
        measurement = _resolve_metric(engine, query)
        actual = measurement.value if isinstance(measurement.value, (int, float)) else None
        ok = actual is not None and _compare(actual, query.expected, query.tolerance, query.comparison)
        if not ok:
            passed = False
            reasons.append(
                f"{query.metric} on {query.subject!r} was {actual}, required "
                f"{query.comparison.value} {query.expected} (tolerance {query.tolerance})"
            )

    forbidden_found: tuple[Defect, ...] = ()
    if query.forbidden_defects:
        forbidden_found = _forbidden_defects_present(engine, query)
        if forbidden_found:
            passed = False
            classes = sorted({d.defect_class.value for d in forbidden_found})
            reasons.append(f"forbidden defect(s) present: {', '.join(classes)}")

    return AcceptanceResult(
        query_id=query.query_id,
        passed=passed,
        actual=actual,
        reason="; ".join(reasons),
        defects=forbidden_found,
    )


def is_watertight(engine: EngineProtocol, object_id: str) -> bool:
    """``True`` iff the object has no boundary holes and no non-manifold edges."""
    return not find_boundary_holes(engine, object_id) and not find_non_manifold_edges(
        engine, object_id
    )
