"""Tests for ``realism_report`` — computable proxies, never a "looks realistic" score.

Research turned up no published metric for overall visual realism
(``docs/research/domain.md``); inventing one would hand an agent a number dressed up as a
fact when it is really an opinion. These tests hold the report to two things: every value it
returns is a genuine, typed ``contracts.MetricKind`` measurement (never an ad hoc string
pretending to be one), and nothing in the report is named or described as an overall score.
"""

from __future__ import annotations

from contracts import Measurement, MetricKind, Vec3
from detail import realism_report
from testing import FakeEngine

_FORBIDDEN_PHRASES = (
    "realism score",
    "quality score",
    "overall realism",
    "overall quality",
    "looks realistic",
    "realism rating",
)


def test_every_measurement_uses_a_real_metric_kind(engine: FakeEngine) -> None:
    """``Measurement.kind`` is typed as ``contracts.MetricKind`` precisely so a caller can
    trust it is one of the seven defined queries rather than a typo'd or invented string that
    type-checks fine and then falls through silently at the point it is actually used."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    report = realism_report(engine, "box")

    assert report, "expected at least one computable proxy"
    for m in report:
        assert isinstance(m, Measurement)
        assert m.kind in MetricKind
        assert m.subject == "box"


def test_at_least_four_proxies_are_reported(engine: FakeEngine) -> None:
    """The module brief names four specific, computable proxies (sharp-edge ratio, triangle
    aspect ratio, edge-length uniformity, triangle count) — a report that collapses them into
    fewer values has quietly dropped one of the named signals."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    report = realism_report(engine, "box")

    assert len(report) >= 4


def test_triangle_count_proxy_matches_the_actual_snapshot(engine: FakeEngine) -> None:
    """Triangle count is the one proxy with an unambiguous existing contract member
    (``MetricKind.TRIANGLE_COUNT``) — a value that disagrees with the object's real triangle
    count would corrupt every polygon-budget decision built on this report."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    expected = engine.snapshot("box").triangle_count

    report = realism_report(engine, "box")

    triangle_counts = [m.value for m in report if m.kind is MetricKind.TRIANGLE_COUNT]
    assert triangle_counts == [expected]


def test_no_measurement_claims_to_be_an_overall_realism_or_quality_score(
    engine: FakeEngine,
) -> None:
    """No published metric for "looks realistic" exists — a measurement that describes
    itself as one would be a fabricated fact with a decimal point attached, and an agent
    reading this report has no way to know it is fake unless the report itself never says
    it."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    report = realism_report(engine, "box")

    for m in report:
        text = f"{m.detail} {m.describe()}".lower()
        for phrase in _FORBIDDEN_PHRASES:
            assert phrase not in text, f"{phrase!r} found in measurement: {m}"


def test_realism_report_never_mutates_the_engine(engine: FakeEngine) -> None:
    """A report is read-only by definition — if it mutated the scene, "checking realism"
    would itself be a side effect an agent has to account for, which is not what a report is
    for."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    before = engine.snapshot("box").triangle_count
    calls_before = len(engine.calls)

    realism_report(engine, "box")

    assert engine.snapshot("box").triangle_count == before
    # FakeEngine only records mutating calls (bevel_edges, set_pbr, ...) in `.calls` — the
    # read-only accessors this report is allowed to use (snapshot, list_objects, exists,
    # world_bounds, material) are never recorded, so any growth here is a mutation.
    assert engine.calls[calls_before:] == []
