"""Stub — ``uv_quality`` and the shared proxy computation ``unwrap`` also reuses.

See ``src/uv/README.md``. Three computable proxies stand in for "is this unwrap any good":
coverage (how much of the ``[0,1]`` UV tile is actually used), max stretch ratio (worst-case
world-area-per-UV-area across triangles) and overlap count (UV-space triangle pairs whose
interiors genuinely intersect, not merely touch along a shared edge). None of these is a
"looks good" verdict — same split of authority ADR-005 draws elsewhere (measurement decides
hard facts, the agent decides appearance) — they are only the numbers that are computable.

**Contract note:** ``contracts.MetricKind`` has seven members and none names any of these
three proxies directly — the same gap ``src/detail/report.py`` already documented and
resolved by reusing an existing kind and carrying the real name in ``Measurement.detail``.
This module follows the same convention rather than editing the frozen contract (Rule 5);
``quality_test.py`` only asserts every returned ``kind`` is a genuine ``MetricKind`` member,
never which one.

Nothing here computes anything yet; every function raises until an implementer replaces the
body (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import EngineProtocol, Measurement, MeshSnapshot, MetricKind

from ._uv_geom import triangles_overlap, uv_triangle_area

__all__ = ["uv_quality", "compute_uv_proxies"]

#: Below this, a UV-space triangle is treated as having no area at all — degenerate rather
#: than merely thin. ``FakeEngine.unwrap``'s planar XY projection produces exactly this for
#: any triangle whose three vertices share the same (x, y): every side face of a cube, since
#: the projection ignores Z entirely.
_UV_AREA_EPS = 1e-9


def compute_uv_proxies(snapshot: MeshSnapshot) -> tuple[float, float, int]:
    """``(coverage, max_stretch, overlap_count)`` — pure, no engine access.

    Shared by :func:`uv_quality` (boxes these into ``Measurement``) and :func:`uv.unwrap`
    (carries them un-boxed on ``UVResult``) so the two can never compute the same three
    numbers by two different formulas that quietly drift apart from each other.

    - **coverage**: sum of every triangle's UV-space area, capped at ``1.0`` — the fraction
      of the ``[0, 1]`` tile that is "painted" by at least one triangle. Overlapping
      triangles would otherwise push the raw sum past 1.0; the cap keeps this a proxy for
      "how full is the tile", not a substitute for :func:`triangles_overlap`'s own count.
    - **max_stretch**: the worst-case ratio of a triangle's world-space area to its UV-space
      area across the mesh. Not a substitute for a proper per-triangle Jacobian/singular-
      value distortion metric (no published one is implemented here, the same caveat
      ``detail.realism_report`` states for its own proxies) — it is the world area mapped
      per unit UV area, so a texture of fixed resolution reads as more visibly stretched or
      blurred wherever this number is larger. Triangles whose UV area is degenerate
      (``< _UV_AREA_EPS``) are excluded from this ratio — their true stretch is unbounded,
      and including them would make the "worst case" always report that one meaningless
      number instead of the worst *measurable* one.
    - **overlap_count**: number of UV-space triangle *pairs* (not triangles) whose interiors
      genuinely intersect, via :func:`triangles_overlap`'s Separating Axis Theorem test.
      Degenerate (near-zero-area) triangles are excluded — they cannot meaningfully overlap
      anything.

    ``snapshot.uvs`` is per-vertex, not per-triangle-corner (``contracts.MeshSnapshot``'s own
    shape) — a simplification inherited from the frozen contract, not invented here. A
    real cut-and-unfold unwrap needs per-corner UVs so the same vertex can carry different
    coordinates on either side of a seam; with only per-vertex UVs available, triangles that
    happen to share world position but belong to different faces (a cube's top vs. bottom,
    under a naive projection) can end up truly indistinguishable in UV space too — which is
    exactly what the overlap counter below is watching for.
    """
    if snapshot.uvs is None:
        return 0.0, 0.0, 0

    uvs = snapshot.uvs
    verts = snapshot.world_vertices()
    triangles = snapshot.triangles

    uv_areas: list[float] = []
    world_areas: list[float] = []
    tri_uvs: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
    for tri in triangles:
        a, b, c = uvs[tri[0]], uvs[tri[1]], uvs[tri[2]]
        tri_uvs.append((a, b, c))
        uv_areas.append(uv_triangle_area(a, b, c))
        wa, wb, wc = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        world_areas.append((wb - wa).cross(wc - wa).length() / 2.0)

    coverage = min(1.0, sum(uv_areas))

    stretch_ratios = [
        world_areas[i] / uv_areas[i] for i in range(len(triangles)) if uv_areas[i] > _UV_AREA_EPS
    ]
    max_stretch = max(stretch_ratios) if stretch_ratios else 0.0

    candidates = [i for i in range(len(triangles)) if uv_areas[i] > _UV_AREA_EPS]
    overlap_count = 0
    for pos_a in range(len(candidates)):
        for pos_b in range(pos_a + 1, len(candidates)):
            i, j = candidates[pos_a], candidates[pos_b]
            if triangles_overlap(tri_uvs[i], tri_uvs[j]):
                overlap_count += 1

    return coverage, max_stretch, overlap_count


def uv_quality(engine: EngineProtocol, object_id: str) -> tuple[Measurement, ...]:
    """Coverage, max stretch ratio and overlap count for ``object_id``'s current UVs.

    Read-only — never calls a mutating ``EngineProtocol`` method. If the object has not been
    unwrapped yet (``snapshot.uvs is None``), every proxy reads as its identity value (0.0
    coverage, 0.0 stretch, 0 overlaps) rather than raising; call :func:`uv.unwrap` first for
    a meaningful report.

    **Contract note:** ``contracts.MetricKind`` has no dedicated member for any of these
    three proxies (see this module's own docstring) — each reuses the existing kind whose
    value shape fits (a bare float, no unit) and carries its real name in
    ``Measurement.detail``, mirroring ``detail/report.py``'s own documented resolution of the
    identical gap. ``quality_test.py`` only asserts every returned ``kind`` is a genuine
    ``MetricKind`` member, never which one.
    """
    snapshot = engine.snapshot(object_id)
    coverage, max_stretch, overlaps = compute_uv_proxies(snapshot)
    return (
        Measurement(
            kind=MetricKind.VOLUME,
            value=coverage,
            unit="",
            subject=object_id,
            detail=(
                "uv coverage: fraction of the [0,1] UV tile occupied by mapped triangles, "
                "capped at 1.0"
            ),
        ),
        Measurement(
            kind=MetricKind.DISTANCE,
            value=max_stretch,
            unit="",
            subject=object_id,
            detail=(
                "uv max stretch ratio: worst measurable (world triangle area / uv triangle "
                "area) across the mesh"
            ),
        ),
        Measurement(
            kind=MetricKind.TRIANGLE_COUNT,
            value=float(overlaps),
            unit="",
            subject=object_id,
            detail=(
                "uv overlap count: number of UV-space triangle pairs whose interiors overlap"
            ),
        ),
    )
