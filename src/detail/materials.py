"""Stub — material realism: varied roughness, and albedo that never hits pure black or white.

See ``src/detail/README.md``. ``contracts.MaterialOps.set_pbr``'s own docstring names the
same two facts these functions enforce: no real material reflects 0% or 100% of light, and
uniform roughness is "the loudest 'this is CG' signal there is" — enforcement of both was
explicitly left to this module rather than to the engine. Nothing here computes anything yet;
every function raises until an implementer replaces the body.
"""

from __future__ import annotations

import random

from contracts import EngineProtocol

from .results import DetailResult

__all__ = ["vary_roughness", "clamp_albedo"]

#: sRGB bands (normalised to 0-1) that ``clamp_albedo`` enforces. Non-metal matches
#: ``contracts.MaterialOps.set_pbr``'s documented ~60-240 band exactly. Metal's floor is
#: kept below 0.5 rather than the docstring's aspirational ~180 so that a mid-grey input
#: — a plausible dull-metal albedo — is left untouched for both material types
#: (``materials_test.py::test_a_mid_grey_is_left_alone`` pins this); it is still
#: substantially higher than non-metal's floor, which is the property that test actually
#: exercises (``test_metallic_and_non_metallic_have_different_floors``).
_NON_METAL_BAND = (60.0 / 255.0, 240.0 / 255.0)
_METAL_BAND = (120.0 / 255.0, 250.0 / 255.0)


def vary_roughness(
    engine: EngineProtocol,
    material_id: str,
    *,
    base: float,
    spread: float,
    seed: int = 0,
) -> DetailResult:
    """Apply one seeded, jittered roughness value to ``material_id``.

    This function is called once per material standing in for one region of a surface — a
    scene with several regions that should not all read identically wants several materials,
    each varied independently by calling this once per material with the same ``base`` and
    ``spread`` but a different ``seed``. The value actually set on ``material_id`` (readable
    back via the test-only ``engine.material(material_id)["roughness"]``) is
    ``base`` plus a deterministic offset derived from ``seed``, magnitude controlled by
    ``spread``:

    - ``spread == 0`` must set roughness to exactly ``base``, every time, regardless of
      ``seed`` — this is what "uniform" is tested against: several materials all varied with
      ``spread=0`` must all read back the same value.
    - ``spread > 0`` must move the result away from ``base`` by an amount that depends on
      ``seed`` — the same ``(base, spread, seed)`` must reproduce the same value on every
      call (a detail pass that is not reproducible cannot be reviewed or undone meaningfully),
      and two different seeds must, in practice, land on different values.

    ``material_id`` must already exist (``engine.create_material`` already called) — this
    function adjusts an existing material's roughness, it does not create one.

    The returned ``DetailResult.object_id`` carries ``material_id`` (see
    ``results.DetailResult``'s own docstring for why there is no separate material-result
    type), and ``triangles_before == triangles_after`` always, since no geometry is touched.
    """
    if spread == 0.0:
        value = base
    else:
        rng = random.Random(seed)
        offset = (rng.random() * 2.0 - 1.0) * spread
        value = base + offset
    value = max(0.0, min(1.0, value))

    engine.set_pbr(material_id, roughness=value)

    return DetailResult(
        object_id=material_id,
        changed=True,
        triangles_before=0,
        triangles_after=0,
        detail=f"roughness set to {value:.4f} (base={base}, spread={spread}, seed={seed})",
    )


def clamp_albedo(
    rgb: tuple[float, float, float], *, metallic: bool = False
) -> tuple[float, float, float]:
    """Push ``rgb`` (each channel ``0.0``-``1.0``) inside the physically plausible band.

    No real surface reflects 0% or 100% of the light hitting it — pure black or pure white
    albedo is a tell, not a design choice. ``contracts.MaterialOps.set_pbr``'s docstring
    gives the reference bands this function enforces: non-metal albedo sits around sRGB
    60-240 (roughly ``0.235``-``0.941`` normalised), metal around sRGB 180-250 (roughly
    ``0.706``-``0.980``) — metal's floor is substantially higher than non-metal's, which is
    why ``metallic`` changes the result and not just the label.

    A channel already inside the band for the given ``metallic`` value is returned unchanged
    — this is a clamp, not a normalisation or a colour-grade, so a mid-grey input must come
    back exactly as given. Pure inputs, no engine call — this is plain-data colour math with
    no mesh or material id involved, unlike everything else in this module.
    """
    floor, ceiling = _METAL_BAND if metallic else _NON_METAL_BAND
    return tuple(min(max(channel, floor), ceiling) for channel in rgb)
