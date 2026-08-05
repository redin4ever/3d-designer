"""Stub — composition: ``inspect``, ``report``, ``evaluate``, ``is_watertight``.

Combines the single-object checks (``topology``), the pairwise checks (``intersections``)
and the metric queries (``metrics``) into the shapes the rest of the system consumes: a
defect list, a scoped report, and a pass/fail acceptance result. ``evaluate`` is the
definition-of-done mechanism (ADR-005) — a re-run measurement, never an agent's claim.
Nothing below is implemented yet — every function raises. Pure: read-only.
"""

from __future__ import annotations

from typing import Sequence

from contracts import (
    AcceptanceQuery,
    AcceptanceResult,
    Defect,
    EngineProtocol,
    JoineryIntent,
    MeasurementReport,
)

__all__ = ["inspect", "report", "evaluate", "is_watertight"]


def inspect(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """Every single-object check, concatenated: the six ``topology`` finders plus
    :func:`measure.find_self_intersections`. Excludes the pairwise checks
    (:func:`measure.find_clipping`, :func:`measure.find_visual_gaps`), which need a second
    object and cannot run from an object id alone.
    """
    raise NotImplementedError("measure.inspect: not implemented")


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
    raise NotImplementedError("measure.report: not implemented")


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
    raise NotImplementedError("measure.evaluate: not implemented")


def is_watertight(engine: EngineProtocol, object_id: str) -> bool:
    """``True`` iff the object has no boundary holes and no non-manifold edges."""
    raise NotImplementedError("measure.is_watertight: not implemented")
