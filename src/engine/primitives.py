"""Primitive mesh construction for ``MeshOps.create_primitive`` — a distinct decision
(geometry generation) split out of ``mesh.py`` to keep that file focused on object
lifecycle. Every builder produces a bmesh centred on the origin spanning **exactly**
``size.x`` x ``size.y`` x ``size.z`` — ``check_primitive_has_expected_world_bounds`` (a
"2m railing" must be 2m) is universal, so this must be exact, not approximate.
"""

from __future__ import annotations

from contracts import EngineError, Vec3

__all__ = ["build_primitive_bmesh"]

_KNOWN = {"cube", "cylinder", "sphere", "plane", "cone", "torus"}
_SEGMENTS = 32


def build_primitive_bmesh(kind: str, size: Vec3):
    """Return a ``bmesh.types.BMesh`` for ``kind``, scaled to ``size``. Raises
    ``engine.unknown_primitive`` for anything outside the six documented kinds."""
    import bmesh
    from mathutils import Matrix

    if kind not in _KNOWN:
        raise EngineError(
            "engine.unknown_primitive",
            f"{kind!r} is not a primitive",
            f"use one of: {', '.join(sorted(_KNOWN))}",
        )

    bm = bmesh.new()
    z_extent = 1.0  # the local Z span of the unscaled shape this builder produces

    if kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    elif kind == "plane":
        v0 = bm.verts.new((-0.5, -0.5, 0.0))
        v1 = bm.verts.new((0.5, -0.5, 0.0))
        v2 = bm.verts.new((0.5, 0.5, 0.0))
        v3 = bm.verts.new((-0.5, 0.5, 0.0))
        bm.faces.new((v0, v1, v2, v3))
    elif kind == "sphere":
        bmesh.ops.create_uvsphere(
            bm, u_segments=_SEGMENTS, v_segments=_SEGMENTS // 2, radius=0.5, calc_uvs=True
        )
    elif kind == "cylinder":
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=_SEGMENTS,
            radius1=0.5, radius2=0.5, depth=1.0, calc_uvs=True,
        )
    elif kind == "cone":
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=_SEGMENTS,
            radius1=0.5, radius2=0.0, depth=1.0, calc_uvs=True,
        )
    else:  # torus — no bmesh.ops builtin; built by hand from two nested loops.
        major, minor = 0.25, 0.25
        z_extent = 2 * minor
        _build_torus(bm, major, minor, _SEGMENTS, _SEGMENTS // 2)

    bm.transform(Matrix.Diagonal((size.x, size.y, size.z / z_extent if z_extent else 0.0, 1.0)))
    bm.normal_update()
    return bm


def _build_torus(bm, major: float, minor: float, major_segments: int, minor_segments: int) -> None:
    import math

    rings = []
    for i in range(major_segments):
        theta = 2 * math.pi * i / major_segments
        ring = []
        for j in range(minor_segments):
            phi = 2 * math.pi * j / minor_segments
            r = major + minor * math.cos(phi)
            x = r * math.cos(theta)
            y = r * math.sin(theta)
            z = minor * math.sin(phi)
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)

    for i in range(major_segments):
        nxt = (i + 1) % major_segments
        for j in range(minor_segments):
            jn = (j + 1) % minor_segments
            bm.faces.new((rings[i][j], rings[nxt][j], rings[nxt][jn], rings[i][jn]))
