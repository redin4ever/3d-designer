"""Tests for ``uv_quality`` — coverage, max stretch ratio, overlap count.

Measurements are located by keyword in ``Measurement.detail`` rather than by
``Measurement.kind`` — ``contracts.MetricKind`` has no dedicated member for any of these
three proxies (see ``quality.py``'s own module docstring for the documented gap, mirroring
``src/detail/report.py``'s), so which existing kind gets reused is an implementation detail
these tests deliberately do not pin down.
"""

from __future__ import annotations

import pytest

from contracts import Measurement, MetricKind, Vec3
from testing import FakeEngine
from uv import unwrap, uv_quality


def _find(report: tuple[Measurement, ...], keyword: str) -> Measurement:
    matches = [m for m in report if keyword in m.detail.lower()]
    assert len(matches) == 1, f"expected exactly one measurement mentioning {keyword!r} in {report}"
    return matches[0]


def test_every_measurement_uses_a_real_metric_kind_and_the_right_subject(
    engine: FakeEngine,
) -> None:
    engine.create_primitive("plane", "plane", Vec3(1.0, 1.0, 0.0))
    unwrap(engine, "plane")

    report = uv_quality(engine, "plane")

    assert len(report) == 3
    for m in report:
        assert isinstance(m, Measurement)
        assert m.kind in MetricKind
        assert m.subject == "plane"


def test_uv_quality_before_any_unwrap_reads_as_zero_and_does_not_crash(
    engine: FakeEngine,
) -> None:
    """An object with no UVs has nothing to measure — this must read as the identity value,
    not raise, so a caller can call ``uv_quality`` speculatively without guarding it."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    report = uv_quality(engine, "box")

    coverage = _find(report, "coverage")
    stretch = _find(report, "stretch")
    overlap = _find(report, "overlap")
    assert coverage.value == pytest.approx(0.0)
    assert stretch.value == pytest.approx(0.0)
    assert overlap.value == pytest.approx(0.0)


def test_coverage_is_within_unit_range_and_full_for_a_single_clean_quad(
    engine: FakeEngine,
) -> None:
    """A lone quad's two triangles exactly tile the unit UV square with no overlap and no
    gap — coverage of anything but ~1.0 here would mean the area computation is wrong."""
    engine.create_primitive("plane", "plane", Vec3(3.0, 2.0, 0.0))
    unwrap(engine, "plane")

    report = uv_quality(engine, "plane")

    coverage = _find(report, "coverage")
    assert 0.0 <= coverage.value <= 1.0
    assert coverage.value == pytest.approx(1.0)


def test_max_stretch_reflects_the_objects_own_scale_not_a_hardcoded_constant(
    engine: FakeEngine,
) -> None:
    """``FakeEngine.unwrap`` always normalises a rectangular plane's bounds to exactly fill
    the unit UV square, so a triangle's UV area is always 0.5 regardless of the plane's real
    size — the world/UV area ratio this module reports is therefore driven entirely by the
    plane's real-world area. A 1x1 m plane and a 2x2 m plane must report different ratios
    (1.0 and 4.0 respectively, worked from world-area-per-triangle / uv-area-per-triangle =
    0.5/0.5 and 2.0/0.5) — a fixed-constant implementation would report the same number for
    both and fail this specific comparison even if it happened to pass one of them alone."""
    engine.create_primitive("small", "plane", Vec3(1.0, 1.0, 0.0))
    engine.create_primitive("big", "plane", Vec3(2.0, 2.0, 0.0))
    unwrap(engine, "small")
    unwrap(engine, "big")

    small_stretch = _find(uv_quality(engine, "small"), "stretch")
    big_stretch = _find(uv_quality(engine, "big"), "stretch")

    assert small_stretch.value == pytest.approx(1.0)
    assert big_stretch.value == pytest.approx(4.0)
    assert big_stretch.value > small_stretch.value


def test_overlap_detector_finds_nothing_on_a_clean_single_quad(engine: FakeEngine) -> None:
    """A lone quad's two triangles only touch along their shared diagonal — establishing
    that the detector is not trivially reporting overlaps everywhere, which is what makes
    the cube test below meaningful."""
    engine.create_primitive("plane", "plane", Vec3(2.0, 2.0, 0.0))
    unwrap(engine, "plane")

    overlap = _find(uv_quality(engine, "plane"), "overlap")

    assert overlap.value == pytest.approx(0.0)


def test_overlap_detector_finds_real_overlaps_on_a_cube(engine: FakeEngine) -> None:
    """``FakeEngine.unwrap`` projects straight onto world XY, ignoring Z — so a cube's top
    face and bottom face, which share the same X/Y footprint, land on exactly the same UV
    triangles. This is a genuine, engine-produced overlap (not a contrived fixture), and it
    is exactly the kind of defect a real unwrap must never leave behind — the whole reason
    this proxy exists (research flagged seam/UV failures as the highest-risk area in v1)."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    unwrap(engine, "box")

    overlap = _find(uv_quality(engine, "box"), "overlap")

    assert overlap.value >= 1


def test_uv_quality_never_mutates_the_engine(engine: FakeEngine) -> None:
    engine.create_primitive("plane", "plane", Vec3(1.0, 1.0, 0.0))
    unwrap(engine, "plane")
    calls_before = len(engine.calls)

    uv_quality(engine, "plane")

    assert engine.calls[calls_before:] == []
