"""Host-surface frames used by semantic surface-mounted operations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from contracts import EPSILON, EngineProtocol, Quat, ToolError, Vec3

__all__ = ["SurfaceFrame", "roof_frame", "wall_frame"]

_UP = Vec3(0, 0, 1)


@dataclass(frozen=True, slots=True)
class SurfaceFrame:
    centre: Vec3
    horizontal: Vec3
    vertical: Vec3
    normal: Vec3
    horizontal_min: float
    horizontal_max: float
    vertical_min: float
    vertical_max: float
    regions: tuple[tuple[tuple[float, float], ...], ...]

    @property
    def width(self) -> float:
        return self.horizontal_max - self.horizontal_min

    @property
    def height(self) -> float:
        return self.vertical_max - self.vertical_min

    def point(self, horizontal: float, vertical: float, normal_offset: float = 0) -> Vec3:
        plane = self.centre.dot(self.normal)
        return (
            self.horizontal * horizontal
            + self.vertical * vertical
            + self.normal * (plane + normal_offset)
        )

    def rotation(self) -> Quat:
        """Quaternion whose local X/Y/Z axes are horizontal/vertical/normal."""
        x, y, z = self.horizontal, self.vertical, self.normal
        m00, m01, m02 = x.x, y.x, z.x
        m10, m11, m12 = x.y, y.y, z.y
        m20, m21, m22 = x.z, y.z, z.z
        trace = m00 + m11 + m22
        if trace > 0:
            s = math.sqrt(trace + 1.0) * 2
            q = Quat(0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s)
        elif m00 > m11 and m00 > m22:
            s = math.sqrt(1.0 + m00 - m11 - m22) * 2
            q = Quat((m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s)
        elif m11 > m22:
            s = math.sqrt(1.0 + m11 - m00 - m22) * 2
            q = Quat((m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s)
        else:
            s = math.sqrt(1.0 + m22 - m00 - m11) * 2
            q = Quat((m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s)
        return q.normalized()


def _triangles(engine: EngineProtocol, object_id: str):
    if not engine.exists(object_id):
        raise ToolError("ops.unknown_target", f"surface host {object_id!r} does not exist", "pass an existing mesh id")
    snap = engine.snapshot(object_id)
    verts = snap.world_vertices()
    out = []
    for tri in snap.triangles:
        a, b, c = (verts[i] for i in tri)
        cross = (b - a).cross(c - a)
        if cross.length() >= EPSILON:
            out.append((a, b, c, cross.normalized(), cross.length() / 2))
    return out


def _build(selected, normal: Vec3, horizontal: Vec3, vertical: Vec3) -> SurfaceFrame:
    regions = tuple(
        tuple((point.dot(horizontal), point.dot(vertical)) for point in tri[:3])
        for tri in selected
    )
    hs = [value[0] for tri in regions for value in tri]
    vs = [value[1] for tri in regions for value in tri]
    plane = sum(point.dot(normal) for tri in selected for point in tri[:3]) / (3 * len(selected))
    hm, hx, vm, vx = min(hs), max(hs), min(vs), max(vs)
    centre = horizontal * ((hm + hx) / 2) + vertical * ((vm + vx) / 2) + normal * plane
    return SurfaceFrame(centre, horizontal, vertical, normal, hm, hx, vm, vx, regions)


def roof_frame(engine: EngineProtocol, object_id: str) -> SurfaceFrame:
    triangles = _triangles(engine, object_id)
    upward = [tri for tri in triangles if tri[3].z > 0.2]
    if not upward:
        raise ToolError("ops.unsupported_surface", f"roof {object_id!r} has no upward planar face", "use a roof mesh with a planar upward exterior face")
    seed = max(upward, key=lambda tri: tri[4])
    normal = seed[3]
    selected = [tri for tri in upward if tri[3].dot(normal) > 0.999]
    horizontal = Vec3(1, 0, 0) if abs(normal.dot(_UP)) > 0.999 else _UP.cross(normal).normalized()
    vertical = normal.cross(horizontal).normalized()
    return _build(selected, normal, horizontal, vertical)


def wall_frame(engine: EngineProtocol, object_id: str, toward: Vec3) -> SurfaceFrame:
    triangles = [tri for tri in _triangles(engine, object_id) if abs(tri[3].z) < 0.1]
    if not triangles:
        raise ToolError("ops.unsupported_surface", f"wall {object_id!r} has no vertical planar face", "use a wall mesh with a vertical exterior face")
    seed = max(triangles, key=lambda tri: tri[3].dot((toward - (tri[0] + tri[1] + tri[2]) * (1 / 3)).normalized()))
    normal = seed[3]
    plane = sum(point.dot(normal) for point in seed[:3]) / 3
    selected = [
        tri for tri in triangles
        if tri[3].dot(normal) > 0.999
        and abs(sum(point.dot(normal) for point in tri[:3]) / 3 - plane) < 1e-3
    ]
    horizontal = _UP.cross(normal).normalized()
    return _build(selected, normal, horizontal, _UP)
