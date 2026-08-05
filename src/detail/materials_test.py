"""Tests for material realism: varied roughness and non-pure albedo.

Uniform roughness is, in the module brief's own words, "the loudest 'this is CG' signal
there is" — so ``vary_roughness``'s tests check the two directions that claim can be wrong in:
appearing uniform when it should not be, and appearing varied when it was asked to be uniform.
``clamp_albedo`` is pure colour math with no engine involved, tested as plain input/output.
"""

from __future__ import annotations

from detail import clamp_albedo, vary_roughness
from testing import FakeEngine


# -------------------------------------------------------------------------------- roughness

def test_spread_zero_leaves_roughness_uniform_across_materials(engine: FakeEngine) -> None:
    """Three materials standing in for three regions of one surface, all varied with
    ``spread=0``, must all read back the exact same roughness — this is what "uniform" means
    here: no accidental jitter sneaking in even when none was asked for."""
    for name in ("region_a", "region_b", "region_c"):
        engine.create_material(name, (0.5, 0.5, 0.5))

    vary_roughness(engine, "region_a", base=0.5, spread=0.0, seed=0)
    vary_roughness(engine, "region_b", base=0.5, spread=0.0, seed=1)
    vary_roughness(engine, "region_c", base=0.5, spread=0.0, seed=2)

    values = {engine.material(n)["roughness"] for n in ("region_a", "region_b", "region_c")}
    assert values == {0.5}


def test_spread_above_zero_produces_real_variation(engine: FakeEngine) -> None:
    """The same three-region setup, now with ``spread > 0`` and a different seed per region,
    must not all collapse back to the same value — that would be a spread parameter that is
    silently ignored, leaving the uniform-roughness tell exactly as loud as before."""
    for name in ("region_a", "region_b", "region_c"):
        engine.create_material(name, (0.5, 0.5, 0.5))

    vary_roughness(engine, "region_a", base=0.5, spread=0.15, seed=0)
    vary_roughness(engine, "region_b", base=0.5, spread=0.15, seed=1)
    vary_roughness(engine, "region_c", base=0.5, spread=0.15, seed=2)

    values = {engine.material(n)["roughness"] for n in ("region_a", "region_b", "region_c")}
    assert len(values) > 1


def test_the_same_seed_reproduces_the_same_roughness(engine: FakeEngine) -> None:
    """A detail pass that is not reproducible cannot be reviewed or undone meaningfully —
    applying the same base/spread/seed to two fresh materials must land on the same value."""
    engine.create_material("mat_x", (0.5, 0.5, 0.5))
    engine.create_material("mat_y", (0.5, 0.5, 0.5))

    vary_roughness(engine, "mat_x", base=0.4, spread=0.2, seed=42)
    vary_roughness(engine, "mat_y", base=0.4, spread=0.2, seed=42)

    assert engine.material("mat_x")["roughness"] == engine.material("mat_y")["roughness"]


def test_vary_roughness_touches_no_geometry(engine: FakeEngine) -> None:
    """This is a material-only pass; ``DetailResult.object_id`` carries the material id
    (there is no separate material-result type), and triangle counts must be equal on both
    sides since no mesh exists to change."""
    engine.create_material("mat_z", (0.5, 0.5, 0.5))

    result = vary_roughness(engine, "mat_z", base=0.5, spread=0.1, seed=0)

    assert result.object_id == "mat_z"
    assert result.triangles_before == result.triangles_after


# ------------------------------------------------------------------------------------ albedo

def test_pure_black_is_moved_inside_the_plausible_range() -> None:
    """No real surface reflects 0% of incident light — a pure-black albedo is a tell, not a
    stylistic choice, and every channel must come back strictly positive."""
    result = clamp_albedo((0.0, 0.0, 0.0))
    assert all(c > 0.0 for c in result)


def test_pure_white_is_moved_inside_the_plausible_range() -> None:
    """No real surface reflects 100% of incident light either — every channel must come back
    strictly below 1.0."""
    result = clamp_albedo((1.0, 1.0, 1.0))
    assert all(c < 1.0 for c in result)


def test_a_mid_grey_is_left_alone() -> None:
    """This is a clamp, not a colour grade — a value already inside the plausible band for
    either material type must be returned unchanged, not nudged toward some canonical grey."""
    grey = (0.5, 0.5, 0.5)
    assert clamp_albedo(grey) == grey
    assert clamp_albedo(grey, metallic=True) == grey


def test_metallic_and_non_metallic_have_different_floors() -> None:
    """``contracts.MaterialOps.set_pbr``'s own docstring gives the reference bands: non-metal
    albedo sits around sRGB 60-240, metal around 180-250 — metal's floor is substantially
    higher. Clamping pure black for each must land on two different values, not the same
    floor with a metallic flag that does nothing."""
    non_metal = clamp_albedo((0.0, 0.0, 0.0), metallic=False)
    metal = clamp_albedo((0.0, 0.0, 0.0), metallic=True)

    assert metal[0] > non_metal[0]
    assert metal[1] > non_metal[1]
    assert metal[2] > non_metal[2]
