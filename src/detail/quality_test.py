"""Tests for the mesh-quality metrics and the bevel acceptance query.

``contracts.MetricKind`` grew ``TRIANGLE_ASPECT_RATIO``, ``SHARP_EDGE_RATIO`` and
``EDGE_LENGTH_UNIFORMITY`` specifically for this work — they were filed as a contract request
twice and deferred twice. Until they existed this module reused ``ANGLE``/``DISTANCE``/
``GAP_WIDTH`` with the proxy's real name buried in ``Measurement.detail``, which meant no
caller could filter or threshold on them and nothing could express "this bevel is too
slivery" as an acceptance query. These tests hold the module to using the real members now
that they exist.
"""

from __future__ import annotations

import pytest

from contracts import AcceptanceQuery, Comparison, MetricKind, Vec3
from detail import (
    SLIVER_CEILING,
    bevel_quality_acceptance,
    edge_length_uniformity,
    mean_triangle_aspect_ratio,
    realism_report,
)
from testing import FakeEngine


def test_an_equilateral_triangle_measures_one(engine: FakeEngine) -> None:
    """The scale the whole ceiling is expressed on: 1.0 is a perfect triangle. If this drifts,
    every threshold built on the metric silently means something else."""
    verts = [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.5, 3 ** 0.5 / 2, 0.0)]
    engine.create_mesh("tri", verts, [(0, 1, 2)])

    assert mean_triangle_aspect_ratio(engine.snapshot("tri")) == pytest.approx(1.0)


def test_a_needle_measures_in_the_hundreds(engine: FakeEngine) -> None:
    """A 1 m x 4 mm sliver is the shape a bevel leaves behind, and the metric has to make it
    obvious — a metric that compresses the difference between a good triangle and a needle
    cannot drive a gate."""
    verts = [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 0.004, 0.0)]
    engine.create_mesh("needle", verts, [(0, 1, 2)])

    assert mean_triangle_aspect_ratio(engine.snapshot("needle")) > 200.0


def test_a_uniform_mesh_has_uniformity_near_zero(engine: FakeEngine) -> None:
    """Coefficient of variation, so 0 means every edge is the same length. A cube's edges are
    not all equal once triangulated (the face diagonals are longer), but the spread stays
    small — the number only becomes large when a mesh's density changes abruptly, which is
    what makes it a useful signal at all."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    assert 0.0 <= edge_length_uniformity(engine.snapshot("box")) < 0.5


# --------------------------------------------------------------------- the acceptance query

def test_the_bevel_acceptance_query_thresholds_the_real_metric() -> None:
    """The detail phase needs something the gate can *re-run*. A query naming
    ``TRIANGLE_ASPECT_RATIO`` with an ``LTE`` comparison is checkable against live geometry;
    a description of a quality goal is not, and ADR-012 removed the override that used to let
    a phase be left anyway."""
    query = bevel_quality_acceptance("tread")

    assert isinstance(query, AcceptanceQuery)
    assert query.metric is MetricKind.TRIANGLE_ASPECT_RATIO
    assert query.comparison is Comparison.LTE
    assert query.subject == "tread"
    assert query.expected == SLIVER_CEILING


def test_the_ceiling_can_be_tightened_per_subject() -> None:
    """A hero prop and a background wall do not deserve the same topology budget. The default
    is calibrated on a stair tread with the default bevel width; a caller with a stricter
    target must be able to say so rather than fork the query."""
    query = bevel_quality_acceptance("hero", ceiling=12.0)

    assert query.expected == 12.0
    assert query.subject == "hero"


def test_the_ceiling_is_a_number_a_real_bevel_can_actually_hit() -> None:
    """An unreachable ceiling is worse than no ceiling: an unattended agent cannot leave the
    phase, and ADR-012 gives it no override. This value is measured, not aspirational — see
    ``bevel_quality_test.py``, which is the test that would fail if it stopped being true."""
    assert 20.0 < SLIVER_CEILING < 120.0


# ------------------------------------------------------------------------- realism report

def test_the_realism_report_uses_the_three_new_metric_kinds(engine: FakeEngine) -> None:
    """Reusing ``ANGLE`` for a sharp-edge ratio meant a caller could not filter or threshold
    on it, and two identically-typed measurements meant two different things. The members
    exist now; carrying the real name in a free-text ``detail`` field instead would leave the
    gap exactly where it was."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    kinds = {m.kind for m in realism_report(engine, "box")}

    assert MetricKind.SHARP_EDGE_RATIO in kinds
    assert MetricKind.TRIANGLE_ASPECT_RATIO in kinds
    assert MetricKind.EDGE_LENGTH_UNIFORMITY in kinds
    assert MetricKind.TRIANGLE_COUNT in kinds
