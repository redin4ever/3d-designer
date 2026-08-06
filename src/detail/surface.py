"""Stub — surface detail: panel lines and greebles.

See ``src/detail/README.md``. Gate A 8.4 names both as part of v1's surface-detail pass,
alongside seams (owned by ``src/uv/``, not here). Nothing here computes anything yet; every
function raises until an implementer replaces the body.
"""

from __future__ import annotations

import random

from contracts import EngineProtocol, Transform, Vec3

from .results import DetailResult

__all__ = ["add_panel_lines", "add_greebles"]

_AXES = ("x", "y", "z")

#: Candidate-cell grid resolution for `add_greebles`'s scatter. Fixed and independent of
#: `density` on purpose: `density` controls the *probability* a given cell spawns (so the
#: seed's randomness has real room to move the total count — see the function body), while
#: this constant controls how finely the surface is sampled.
_GREEBLE_GRID = 20


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
    if spacing <= 0:
        raise ValueError("detail.add_panel_lines: spacing must be positive")
    if depth <= 0:
        raise ValueError("detail.add_panel_lines: depth must be positive")
    if axis not in _AXES:
        raise ValueError(f"detail.add_panel_lines: axis must be one of {_AXES}, got {axis!r}")

    triangles_before = engine.snapshot(object_id).triangle_count
    bounds = engine.world_bounds(object_id)
    size = bounds.size.as_tuple()

    axis_index = _AXES.index(axis)
    remaining = [i for i in range(3) if i != axis_index]
    # `depth` cuts inward along whichever remaining axis isn't the groove's own spacing
    # axis; prefer Z (the outward-facing surface for most assets) unless the caller asked
    # for grooves spaced along Z itself, in which case fall back to the first remaining axis.
    depth_index = 2 if axis_index != 2 else remaining[0]
    span_index = remaining[0] if remaining[0] != depth_index else remaining[1]

    axis_extent = size[axis_index]
    line_count = int(axis_extent // spacing)
    if line_count < 1:
        return DetailResult(
            object_id=object_id,
            changed=False,
            triangles_before=triangles_before,
            triangles_after=triangles_before,
            detail="object too small along axis for even one panel line at this spacing",
        )

    groove_width = max(min(spacing * 0.2, spacing * 0.5), 1e-6)
    span_margin = size[span_index] * 0.1 + 1e-6

    def _vec(axis_val: float, span_val: float, depth_val: float) -> Vec3:
        components = [0.0, 0.0, 0.0]
        components[axis_index] = axis_val
        components[span_index] = span_val
        components[depth_index] = depth_val
        return Vec3(*components)

    cutter_size = _vec(groove_width, size[span_index] + span_margin, depth * 1.02)
    centre_span = bounds.centre.as_tuple()[span_index]
    depth_max = bounds.maximum.as_tuple()[depth_index]

    axis_min = bounds.minimum.as_tuple()[axis_index]
    axis_max = bounds.maximum.as_tuple()[axis_index]
    start = axis_min + spacing / 2.0

    cut_count = 0
    for i in range(line_count):
        pos = start + i * spacing
        if pos >= axis_max:
            break
        centre = _vec(pos, centre_span, depth_max - depth / 2.0)
        cutter_id = engine.create_primitive(
            f"__panel_cutter_{object_id}_{i}", "cube", cutter_size, Transform(translation=centre)
        )
        engine.boolean(object_id, cutter_id, "difference")
        cut_count += 1

    if cut_count == 0:
        return DetailResult(
            object_id=object_id,
            changed=False,
            triangles_before=triangles_before,
            triangles_after=triangles_before,
            detail="object too small along axis for even one panel line at this spacing",
        )

    triangles_after = engine.snapshot(object_id).triangle_count
    return DetailResult(
        object_id=object_id,
        changed=True,
        triangles_before=triangles_before,
        triangles_after=triangles_after,
        detail=f"cut {cut_count} panel line(s) along {axis}, depth={depth}m",
    )


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
    if not 0.0 <= rest_fraction <= 1.0:
        raise ValueError("detail.add_greebles: rest_fraction must be within [0, 1]")
    if density < 0:
        raise ValueError("detail.add_greebles: density must be non-negative")

    triangles_before = engine.snapshot(object_id).triangle_count
    bounds = engine.world_bounds(object_id)
    footprint_x = bounds.size.x if bounds.size.x > 1e-9 else 1.0
    footprint_y = bounds.size.y if bounds.size.y > 1e-9 else 1.0

    rng = random.Random(seed)

    grid_n = _GREEBLE_GRID
    cell_w = footprint_x / grid_n
    cell_h = footprint_y / grid_n
    cell_area = cell_w * cell_h

    # Reserve a contiguous horizontal band of rows as the "calm" region — a real region a
    # viewer reads as deliberate, never a speckle of individually-skipped cells.
    rest_rows = round(rest_fraction * grid_n)
    rest_start = rng.randrange(0, grid_n - rest_rows + 1)
    rest_row_set = set(range(rest_start, rest_start + rest_rows))

    spawn_probability = min(1.0, density * cell_area)
    greeble_size = max(1e-4, min(cell_w, cell_h) * 0.3)
    surface_z = bounds.maximum.z

    spawn_count = 0
    for row in range(grid_n):
        if row in rest_row_set:
            continue
        for col in range(grid_n):
            if rng.random() >= spawn_probability:
                continue
            jitter_x = rng.uniform(-0.3, 0.3) * cell_w
            jitter_y = rng.uniform(-0.3, 0.3) * cell_h
            gx = bounds.minimum.x + (col + 0.5) * cell_w + jitter_x
            gy = bounds.minimum.y + (row + 0.5) * cell_h + jitter_y
            gz = surface_z + greeble_size / 2.0
            greeble_id = engine.create_primitive(
                f"__greeble_{object_id}_{spawn_count}",
                "cube",
                Vec3(greeble_size, greeble_size, greeble_size),
                Transform(translation=Vec3(gx, gy, gz)),
            )
            engine.join(object_id, [greeble_id])
            spawn_count += 1

    if spawn_count == 0:
        return DetailResult(
            object_id=object_id,
            changed=False,
            triangles_before=triangles_before,
            triangles_after=triangles_before,
            detail="no greeble qualified — rest_fraction reserved the whole surface or "
            "density rounded down to nothing",
        )

    triangles_after = engine.snapshot(object_id).triangle_count
    return DetailResult(
        object_id=object_id,
        changed=True,
        triangles_before=triangles_before,
        triangles_after=triangles_after,
        detail=f"scattered {spawn_count} greeble(s), rest_fraction={rest_fraction}, seed={seed}",
    )
