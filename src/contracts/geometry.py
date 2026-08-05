"""Plain-data geometry value types.

Nothing in this file imports bpy, numpy or any engine. These are the types every module
outside ``src/engine/`` speaks, which is what makes the decision layer testable with no
Blender installed (ADR-008).

Units: **metres**, always, inside this boundary. Engine export profiles convert at the
edge and nothing upstream of ``src/export/`` knows about engine conventions (ADR-010).
Axis convention inside the boundary is Blender-native **Z-up, right-handed**.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = [
    "Vec3",
    "Quat",
    "Transform",
    "AABB",
    "MeshSnapshot",
    "EPSILON",
]

#: Default tolerance in metres. Two points closer than this are the same point.
#: Chosen at 0.1 mm: tighter than any modelling tolerance we care about, looser than
#: float32 accumulation error over a scene tens of metres across.
EPSILON = 1e-4


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, k: float) -> "Vec3":
        return Vec3(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> "Vec3":
        n = self.length()
        if n < EPSILON:
            raise ValueError("cannot normalize a zero-length vector")
        return Vec3(self.x / n, self.y / n, self.z / n)

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


#: World up. Blender-native Z-up (ADR-010). "Plumb" means parallel to this, and it is
#: deliberately NOT the path normal — posts normal to a stair rake is the single most
#: common naive-generator error the product exists to prevent.
WORLD_UP = Vec3(0.0, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class Quat:
    """Unit quaternion, w-first.

    Rotation is stored and composed as a quaternion internally and only converted to
    Euler at the agent-facing parameter surface (Gate A decision, ADR-004). Compounding
    Euler edits across hundreds of agent operations accumulates gimbal-lock error; this
    type is what prevents that.
    """

    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @staticmethod
    def identity() -> "Quat":
        return Quat()

    @staticmethod
    def from_axis_angle(axis: Vec3, radians: float) -> "Quat":
        a = axis.normalized()
        h = radians * 0.5
        s = math.sin(h)
        return Quat(math.cos(h), a.x * s, a.y * s, a.z * s)

    def __mul__(self, other: "Quat") -> "Quat":
        w1, x1, y1, z1 = self.w, self.x, self.y, self.z
        w2, x2, y2, z2 = other.w, other.x, other.y, other.z
        return Quat(
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        )

    def normalized(self) -> "Quat":
        n = math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)
        if n < EPSILON:
            raise ValueError("cannot normalize a zero quaternion")
        return Quat(self.w / n, self.x / n, self.y / n, self.z / n)

    def rotate(self, v: Vec3) -> Vec3:
        u = Vec3(self.x, self.y, self.z)
        s = self.w
        return 2.0 * u.dot(v) * u + (s * s - u.dot(u)) * v + 2.0 * s * u.cross(v)


@dataclass(frozen=True, slots=True)
class Transform:
    translation: Vec3 = field(default_factory=Vec3)
    rotation: Quat = field(default_factory=Quat)
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))

    @staticmethod
    def identity() -> "Transform":
        return Transform()

    def is_uniformly_scaled(self, tol: float = EPSILON) -> bool:
        return (
            abs(self.scale.x - self.scale.y) < tol
            and abs(self.scale.y - self.scale.z) < tol
        )

    def has_unapplied_scale(self, tol: float = EPSILON) -> bool:
        """Unapplied non-unit scale silently corrupts bevel width, boolean results and
        physics, and is invisible in a viewport. It is one of the eight defect classes
        precisely because it cannot be seen — only measured."""
        return (
            abs(self.scale.x - 1.0) > tol
            or abs(self.scale.y - 1.0) > tol
            or abs(self.scale.z - 1.0) > tol
        )

    def apply(self, v: Vec3) -> Vec3:
        scaled = Vec3(v.x * self.scale.x, v.y * self.scale.y, v.z * self.scale.z)
        return self.rotation.rotate(scaled) + self.translation


@dataclass(frozen=True, slots=True)
class AABB:
    """Axis-aligned bounding box in world space."""

    minimum: Vec3
    maximum: Vec3

    @staticmethod
    def from_points(points: Iterable[Vec3]) -> "AABB":
        pts = list(points)
        if not pts:
            raise ValueError("cannot build an AABB from no points")
        return AABB(
            Vec3(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            Vec3(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)),
        )

    @property
    def size(self) -> Vec3:
        return self.maximum - self.minimum

    @property
    def centre(self) -> Vec3:
        return (self.minimum + self.maximum) * 0.5

    def overlaps(self, other: "AABB", tol: float = 0.0) -> bool:
        return (
            self.minimum.x - tol <= other.maximum.x
            and self.maximum.x + tol >= other.minimum.x
            and self.minimum.y - tol <= other.maximum.y
            and self.maximum.y + tol >= other.minimum.y
            and self.minimum.z - tol <= other.maximum.z
            and self.maximum.z + tol >= other.minimum.z
        )

    def expanded(self, margin: float) -> "AABB":
        m = Vec3(margin, margin, margin)
        return AABB(self.minimum - m, self.maximum + m)


@dataclass(frozen=True, slots=True)
class MeshSnapshot:
    """A neutral, bpy-free view of one object's evaluated geometry.

    **This type is the entire boundary between the geometry engine and everything else.**
    ``src/engine/`` produces it; every other module consumes it and never sees bpy.

    ``vertices`` are in the object's local space; ``transform`` places them in the world.
    ``triangles`` index into ``vertices``. Non-triangular faces are triangulated by the
    engine before a snapshot is produced, so consumers never handle n-gons — but
    ``polygon_count`` records the pre-triangulation count, because polygon budgets and
    topology quality are stated in faces, not triangles.
    """

    object_id: str
    vertices: Sequence[Vec3]
    triangles: Sequence[tuple[int, int, int]]
    transform: Transform = field(default_factory=Transform)
    normals: Sequence[Vec3] | None = None
    uvs: Sequence[tuple[float, float]] | None = None
    polygon_count: int = 0
    material_slots: Sequence[str] = ()

    @property
    def triangle_count(self) -> int:
        return len(self.triangles)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    def world_vertices(self) -> list[Vec3]:
        return [self.transform.apply(v) for v in self.vertices]

    def world_bounds(self) -> AABB:
        return AABB.from_points(self.world_vertices())
