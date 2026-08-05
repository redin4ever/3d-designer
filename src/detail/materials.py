"""Stub — material realism: varied roughness, and albedo that never hits pure black or white.

See ``src/detail/README.md``. ``contracts.MaterialOps.set_pbr``'s own docstring names the
same two facts these functions enforce: no real material reflects 0% or 100% of light, and
uniform roughness is "the loudest 'this is CG' signal there is" — enforcement of both was
explicitly left to this module rather than to the engine. Nothing here computes anything yet;
every function raises until an implementer replaces the body.
"""

from __future__ import annotations

from contracts import EngineProtocol

from .results import DetailResult

__all__ = ["vary_roughness", "clamp_albedo"]


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
    raise NotImplementedError("detail.vary_roughness: not implemented")


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
    raise NotImplementedError("detail.clamp_albedo: not implemented")
