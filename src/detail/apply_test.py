"""Tests for ``apply_edge_treatment`` — running the heuristic bevel against a live object.

Three product-level guarantees, each with its own test: the engine's own unapplied-scale
refusal must reach the caller rather than being swallowed (an agent that never sees this error
will ship an object with an uneven bevel and no idea why); a real pass must be reported as one
(more triangles, both counts visible); and a pass that found nothing to do must be reported as
a no-op, not as quiet success (Gate A 4.1's "what changed" contract breaks the moment "nothing"
and "something happened silently" look the same in the result).
"""

from __future__ import annotations

import pytest

from contracts import EngineError, Transform, Vec3
from detail import apply_edge_treatment
from testing import FakeEngine


def test_unapplied_scale_surfaces_as_an_engine_error(engine: FakeEngine) -> None:
    """Bevel width is computed in object space, so an unapplied non-uniform scale silently
    produces an uneven bevel — the engine refuses for exactly this reason
    (``ModifierOps.bevel_edges``'s own docstring, and ``FakeEngine.bevel_edges`` enforces it).
    If ``apply_edge_treatment`` caught and hid that error, an agent would ship the corrupted
    bevel with no signal anything went wrong."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    engine.set_transform("box", Transform(scale=Vec3(2.0, 1.0, 1.0)))

    with pytest.raises(EngineError):
        apply_edge_treatment(engine, "box")


def test_a_real_pass_increases_triangle_count_and_reports_both_counts(
    engine: FakeEngine,
) -> None:
    """Gate A 4.1: feedback after any change must include what changed plus key
    measurements. A bevel that ran but reported identical before/after counts would be
    indistinguishable from one that silently did nothing."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    before = engine.snapshot("box").triangle_count

    result = apply_edge_treatment(engine, "box")

    after = engine.snapshot("box").triangle_count
    assert result.object_id == "box"
    assert result.changed is True
    assert result.triangles_before == before
    assert result.triangles_after == after
    assert result.triangles_after > result.triangles_before


def test_nothing_qualifying_is_reported_as_a_no_op_not_success(engine: FakeEngine) -> None:
    """A single flat plane has no edge with two adjacent, non-coplanar faces — nothing
    qualifies for a bevel at all. Reporting ``changed=True`` here would be the false-success
    shape Gate A 4.2 exists to rule out: an agent reading the result would believe a bevel was
    applied when the geometry never moved."""
    engine.create_primitive("flat", "plane", Vec3(2.0, 2.0, 1.0))
    before = engine.snapshot("flat").triangle_count

    result = apply_edge_treatment(engine, "flat")

    after = engine.snapshot("flat").triangle_count
    assert result.changed is False
    assert result.triangles_before == before
    assert result.triangles_after == after
    assert before == after
