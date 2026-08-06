"""Tests for surface detail: panel lines and greebles.

Greebles carry the heavier test load because the module brief calls out three specific,
checkable properties for them: a ``rest_fraction`` of 1.0 must add nothing, 0.0 must greeble
everywhere, and the pass must be reproducible by seed. Panel lines get a lighter structural
check — the interface must exist and behave like every other pass in this module (never
reports fewer triangles than it started with) — since the module brief does not itemise
panel-line-specific behaviour the way it does for greebles.
"""

from __future__ import annotations

from contracts import Vec3
from detail import add_greebles, add_panel_lines
from testing import FakeEngine


# ------------------------------------------------------------------------------ panel lines

def test_panel_lines_never_reduce_triangle_count(engine: FakeEngine) -> None:
    """Panel lines are cut into the surface, not merged away — a pass that reports fewer
    triangles than it started with has done something other than add a groove, regardless of
    what its ``detail`` text claims."""
    engine.create_primitive("hull", "cube", Vec3(4.0, 2.0, 1.0))
    before = engine.snapshot("hull").triangle_count

    result = add_panel_lines(engine, "hull", spacing=0.5, depth=0.02, axis="z")

    after = engine.snapshot("hull").triangle_count
    assert result.object_id == "hull"
    assert result.triangles_before == before
    assert result.triangles_after == after
    assert result.triangles_after >= result.triangles_before


# ---------------------------------------------------------------------------------- greebles

def test_rest_fraction_one_adds_nothing(engine: FakeEngine) -> None:
    """``rest_fraction=1.0`` reserves the entire surface as deliberately calm — greebling
    every last region would be greebling uniformly, which the module brief says reads as
    noise, not detail. This must come back as a genuine no-op, the same honesty requirement
    ``apply_edge_treatment`` holds to for an empty edge selection."""
    engine.create_primitive("panel", "plane", Vec3(4.0, 4.0, 1.0))
    before = engine.snapshot("panel").triangle_count

    result = add_greebles(engine, "panel", density=2.0, rest_fraction=1.0, seed=0)

    after = engine.snapshot("panel").triangle_count
    assert result.changed is False
    assert result.triangles_before == before
    assert result.triangles_after == after == before


def test_rest_fraction_zero_greebles_everywhere(engine: FakeEngine) -> None:
    """With no area reserved calm, any nonzero density must actually add geometry somewhere
    on the surface — a ``rest_fraction=0.0`` call that changes nothing means the density
    parameter is not wired up at all."""
    engine.create_primitive("panel", "plane", Vec3(4.0, 4.0, 1.0))
    before = engine.snapshot("panel").triangle_count

    result = add_greebles(engine, "panel", density=2.0, rest_fraction=0.0, seed=0)

    after = engine.snapshot("panel").triangle_count
    assert result.changed is True
    assert after > before
    assert result.triangles_after == after


def test_the_same_seed_reproduces_the_same_result(engine: FakeEngine) -> None:
    """A detail pass that is not reproducible cannot be reviewed or undone meaningfully
    (module brief) — the same starting geometry and the same seed must land on the same
    triangle count on two independent objects, not merely "close"."""
    engine.create_primitive("panel_a", "plane", Vec3(4.0, 4.0, 1.0))
    engine.create_primitive("panel_b", "plane", Vec3(4.0, 4.0, 1.0))

    result_a = add_greebles(engine, "panel_a", density=3.0, rest_fraction=0.0, seed=7)
    result_b = add_greebles(engine, "panel_b", density=3.0, rest_fraction=0.0, seed=7)

    assert result_a.triangles_after == result_b.triangles_after
    assert engine.snapshot("panel_a").triangle_count == engine.snapshot("panel_b").triangle_count


def test_different_seeds_produce_different_results(engine: FakeEngine) -> None:
    """If every seed produced the same scatter, ``seed`` would be a decorative parameter — an
    agent asked to "try a different variation" would get the identical result back every
    time. A high density over a generous surface makes an accidental collision between two
    different seeds implausible for any real scatter implementation."""
    engine.create_primitive("panel_c", "plane", Vec3(6.0, 6.0, 1.0))
    engine.create_primitive("panel_d", "plane", Vec3(6.0, 6.0, 1.0))

    result_c = add_greebles(engine, "panel_c", density=5.0, rest_fraction=0.0, seed=1)
    result_d = add_greebles(engine, "panel_d", density=5.0, rest_fraction=0.0, seed=2)

    assert result_c.triangles_after != result_d.triangles_after
