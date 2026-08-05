"""Stub — surface detail: panel lines and greebles.

See ``src/detail/README.md``. Gate A 8.4 names both as part of v1's surface-detail pass,
alongside seams (owned by ``src/uv/``, not here). Nothing here computes anything yet; every
function raises until an implementer replaces the body.
"""

from __future__ import annotations

from contracts import EngineProtocol

from .results import DetailResult

__all__ = ["add_panel_lines", "add_greebles"]


def add_panel_lines(
    engine: EngineProtocol,
    object_id: str,
    *,
    spacing: float,
    depth: float,
    axis: str = "z",
) -> DetailResult:
    """Cut evenly-spaced grooves into ``object_id`` along ``axis``.

    ``spacing`` and ``depth`` are in metres, in the same object-local units as everything
    else in this module. ``axis`` selects which world axis the lines run perpendicular to
    (one of ``"x"``, ``"y"``, ``"z"``) — panel lines on a wall run differently than panel
    lines on a hull plate, and the caller decides which, this function does not guess.

    Once implemented: a groove pass adds geometry (it cuts, it does not just mark an
    attribute), so ``triangles_after`` must never be less than ``triangles_before``, and
    ``changed`` must be ``False`` on an object too small for even one groove to fit within
    ``spacing`` — reporting a groove that was not actually cut is the same false-success
    shape ``apply_edge_treatment``'s no-op case exists to rule out.
    """
    raise NotImplementedError("detail.add_panel_lines: not implemented")


def add_greebles(
    engine: EngineProtocol,
    object_id: str,
    *,
    density: float,
    rest_fraction: float = 0.4,
    seed: int = 0,
) -> DetailResult:
    """Scatter small relief detail ("greebles") across ``object_id``'s exposed surface.

    ``density`` controls roughly how many greebles per unit area are attempted;
    ``rest_fraction`` is the fraction of that surface deliberately left calm —
    greebling *uniformly* reads as noise, not detail, so a competent implementation reserves
    part of the surface (chosen by ``seed``, contiguous regions rather than a random speckle
    of individual skipped spots, so the calm areas read as deliberate rather than as gaps) and
    never scatters into it.

    ``rest_fraction=1.0`` means the entire surface is reserved calm — nothing is scattered,
    and this must come back as a reported no-op (``changed=False``,
    ``triangles_before == triangles_after``), same reasoning as
    ``apply_edge_treatment``'s empty-selection case. ``rest_fraction=0.0`` means no area is
    reserved, so with any nonzero ``density`` the whole surface is eligible.

    **Reproducibility.** The same ``(object_id geometry, density, rest_fraction, seed)`` must
    produce the same result every time — greebles are geometry an agent or a human may later
    need to review or undo, and "a detail pass that is not reproducible cannot be reviewed or
    undone meaningfully" (module brief). Concretely: seed the RNG this function uses from
    ``seed`` and nothing else (no wall-clock time, no object id hash mixed in without also
    being part of the documented contract) — two identically-shaped objects greebled with the
    same seed must end up with the same triangle count; two different seeds should, in
    practice, produce different counts (see ``surface_test.py`` for the exact assertions).
    """
    raise NotImplementedError("detail.add_greebles: not implemented")
