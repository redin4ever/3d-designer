"""``FakeEngine`` — a pure-Python ``EngineProtocol`` implementation with no bpy.

This is the piece that makes the architecture testable. Every module except
``src/engine/`` is written against ``EngineProtocol`` and receives an implementation at
the composition root; in tests, that implementation is this one. Consequently the whole
decision layer runs its suite with no Blender installed, in milliseconds.

It is a **real** in-memory mesh engine, not a mock that records calls. A mock that only
records calls lets a wrong implementation pass, because the test asserts on the
conversation rather than the outcome. This produces actual vertices, so a test can assert
that a railing post ended up plumb instead of asserting that ``set_transform`` was called.

Owned by the main agent (Rule 5): every module's tests depend on it, so no module agent
may change it. A module needing different behaviour files a contract request.


**Over the 300-line soft cap, deliberately** (Rule 2): this is one class implementing one
frozen Protocol, and every method is there because ``contracts.EngineProtocol`` declares it.
Splitting on any seam other than the Protocol's own mixin boundaries would scatter that
correspondence, and splitting on those would produce five files whose contents are dictated
by a file in another package — the "first half" cut the rule names as a bad seam. It sits at
a third of the hard cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from contracts import AABB, EngineError, MeshSnapshot, Quat, RepairOutcome, Transform, Vec3

from .fake_surfacing import FakeSurfacingMixin
from .mesh_helpers import (
    arc_length_to,
    boundary_loops,
    connected_components,
    rotation_from_up_to,
    sample_polyline,
    tangent_at,
    unit_cube,
)

__all__ = ["FakeEngine", "FakeObject"]


@dataclass
class FakeObject:
    object_id: str
    vertices: list[Vec3]
    faces: list[tuple[int, ...]]
    transform: Transform = field(default_factory=Transform)
    materials: list[str] = field(default_factory=list)
    seams: set[int] = field(default_factory=set)
    unwrapped: bool = False
    uvs: list[tuple[float, float]] | None = None

    def triangulated(self) -> list[tuple[int, int, int]]:
        tris: list[tuple[int, int, int]] = []
        for f in self.faces:
            for i in range(1, len(f) - 1):
                tris.append((f[0], f[i], f[i + 1]))
        return tris


class FakeEngine(FakeSurfacingMixin):
    """In-memory ``EngineProtocol``. Deterministic, fast, bpy-free."""

    backend_name = "fake"

    def __init__(self, *, bake_supported: bool = True) -> None:
        self._objects: dict[str, FakeObject] = {}
        self._materials: dict[str, dict] = {}
        self._counter = 0
        self._bake_supported = bake_supported
        self.calls: list[tuple[str, tuple]] = []
        """Recorded for the rare test that genuinely needs to assert an interaction — that
        a boolean used the ``exact`` solver, say, where the geometric outcome cannot show
        the difference. Assert on geometry first; reach for this only when it cannot."""

    # ---------------------------------------------------------------- internals

    def _record(self, name: str, *args) -> None:
        self.calls.append((name, args))

    def _get(self, object_id: str) -> FakeObject:
        obj = self._objects.get(object_id)
        if obj is None:
            raise EngineError(
                rule="engine.unknown_object",
                detail=f"no object named {object_id!r}",
                suggestion=f"known objects: {', '.join(sorted(self._objects)) or '(none)'}",
            )
        return obj

    def _unique(self, object_id: str) -> str:
        if object_id not in self._objects:
            return object_id
        self._counter += 1
        return f"{object_id}.{self._counter:03d}"

    # ---------------------------------------------------------------- MeshOps

    def create_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
        transform: Transform | None = None,
    ) -> str:
        if not vertices:
            raise EngineError("engine.empty_mesh", "a mesh needs at least one vertex")
        oid = self._unique(object_id)
        self._objects[oid] = FakeObject(
            object_id=oid,
            vertices=list(vertices),
            faces=[tuple(f) for f in faces],
            transform=transform or Transform(),
        )
        self._record("create_mesh", oid)
        return oid

    def replace_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
    ) -> None:
        """Swap geometry, keep everything that is not geometry.

        Transform, material slots and the unwrapped flag survive; that is the whole point
        of this existing alongside delete-then-``create_mesh``.

        The UV layer is the one thing that *cannot* survive, and it is dropped honestly
        rather than kept and left wrong: UVs are stored per split vertex, so a new vertex
        set has no correspondence to the old coordinates. Seams are indices into the old
        edge numbering and go with it. A caller that needs UVs after this re-unwraps —
        which is a real cost, and better than a silently mismatched unwrap.
        """
        obj = self._get(object_id)
        if not vertices:
            raise EngineError(
                "engine.empty_mesh",
                "a mesh needs at least one vertex",
                "pass the replacement geometry, or call delete() if the object should go",
            )
        obj.vertices = list(vertices)
        obj.faces = [tuple(f) for f in faces]
        obj.uvs = None
        obj.unwrapped = False
        obj.seams = set()
        self._record("replace_mesh", object_id)

    def create_primitive(
        self, object_id: str, kind: str, size: Vec3, transform: Transform | None = None
    ) -> str:
        known = {"cube", "cylinder", "sphere", "plane", "cone", "torus"}
        if kind not in known:
            raise EngineError(
                "engine.unknown_primitive",
                f"{kind!r} is not a primitive",
                f"use one of: {', '.join(sorted(known))}",
            )
        if kind == "plane":
            hx, hy = size.x / 2, size.y / 2
            verts = [Vec3(-hx, -hy, 0), Vec3(hx, -hy, 0), Vec3(hx, hy, 0), Vec3(-hx, hy, 0)]
            faces: list[tuple[int, ...]] = [(0, 1, 2, 3)]
        else:
            # Non-planar primitives are approximated by their bounding box. The fake
            # exists to exercise placement, measurement and bookkeeping — not to
            # reproduce Blender's tessellation, which no test should depend on.
            verts, faces = unit_cube(size)
        return self.create_mesh(object_id, verts, faces, transform)

    def duplicate(self, object_id: str, new_id: str, transform: Transform | None = None) -> str:
        src = self._get(object_id)
        oid = self._unique(new_id)
        self._objects[oid] = FakeObject(
            object_id=oid,
            vertices=list(src.vertices),
            faces=list(src.faces),
            transform=transform or src.transform,
            materials=list(src.materials),
        )
        self._record("duplicate", object_id, oid)
        return oid

    def delete(self, object_id: str) -> None:
        self._get(object_id)
        del self._objects[object_id]
        self._record("delete", object_id)

    def set_transform(self, object_id: str, transform: Transform) -> None:
        self._get(object_id).transform = transform
        self._record("set_transform", object_id)

    def apply_transform(
        self, object_id: str, *, location: bool, rotation: bool, scale: bool
    ) -> None:
        obj = self._get(object_id)
        t = obj.transform
        new_verts = []
        for v in obj.vertices:
            w = v
            if scale:
                w = Vec3(w.x * t.scale.x, w.y * t.scale.y, w.z * t.scale.z)
            if rotation:
                w = t.rotation.rotate(w)
            if location:
                w = w + t.translation
            new_verts.append(w)
        obj.vertices = new_verts
        obj.transform = Transform(
            translation=Vec3() if location else t.translation,
            rotation=Quat.identity() if rotation else t.rotation,
            scale=Vec3(1, 1, 1) if scale else t.scale,
        )
        self._record("apply_transform", object_id)

    def join(self, target_id: str, source_ids: Sequence[str]) -> str:
        target = self._get(target_id)
        for sid in source_ids:
            src = self._get(sid)
            offset = len(target.vertices)
            for v in src.vertices:
                world = src.transform.apply(v)
                target.vertices.append(world - target.transform.translation)
            target.faces.extend(tuple(i + offset for i in f) for f in src.faces)
            del self._objects[sid]
        self._record("join", target_id, tuple(source_ids))
        return target_id

    def separate_loose(self, object_id: str) -> list[str]:
        obj = self._get(object_id)
        components = connected_components(len(obj.vertices), obj.faces)
        if len(components) <= 1:
            return [object_id]
        produced = []
        for idx, comp in enumerate(components):
            remap = {old: new for new, old in enumerate(sorted(comp))}
            verts = [obj.vertices[o] for o in sorted(comp)]
            faces = [tuple(remap[i] for i in f) for f in obj.faces if set(f) <= comp]
            produced.append(
                self.create_mesh(f"{object_id}_part{idx}", verts, faces, obj.transform)
            )
        del self._objects[object_id]
        self._record("separate_loose", object_id)
        return produced

    def snapshot(self, object_id: str) -> MeshSnapshot:
        obj = self._get(object_id)
        return MeshSnapshot(
            object_id=obj.object_id,
            vertices=list(obj.vertices),
            triangles=obj.triangulated(),
            transform=obj.transform,
            uvs=list(obj.uvs) if obj.uvs else None,
            polygon_count=len(obj.faces),
            material_slots=tuple(obj.materials),
            material_definitions={
                name: dict(self._materials[name].get("texture") or {})
                for name in obj.materials
                if name in self._materials and self._materials[name].get("texture")
            },
        )

    def list_objects(self) -> list[str]:
        return sorted(self._objects)

    def exists(self, object_id: str) -> bool:
        return object_id in self._objects

    def world_bounds(self, object_id: str) -> AABB:
        return self.snapshot(object_id).world_bounds()

    # ---------------------------------------------------------------- ModifierOps

    def bevel_edges(
        self,
        object_id: str,
        width: float,
        segments: int = 2,
        edge_indices: Sequence[int] | None = None,
    ) -> None:
        obj = self._get(object_id)
        if width <= 0:
            raise EngineError("engine.bad_bevel_width", f"width {width} must be positive")
        if obj.transform.has_unapplied_scale():
            raise EngineError(
                "engine.unapplied_scale",
                f"{object_id} has unapplied scale {obj.transform.scale.as_tuple()}",
                "apply scale before bevelling — bevel width is computed in object space, "
                "so an unapplied scale produces uneven bevels",
            )
        count = len(edge_indices) if edge_indices is not None else len(obj.faces) * 2
        # Model the polygon growth so budget tests are meaningful: a bevel replaces each
        # selected edge with `segments` strips.
        obj.faces.extend([obj.faces[0]] * (count * max(1, segments)))
        self._record("bevel_edges", object_id, width, segments, count)

    def boolean(self, target_id: str, cutter_id: str, mode: str, solver: str = "exact") -> None:
        if mode not in {"union", "difference", "intersect"}:
            raise EngineError("engine.bad_boolean_mode", f"{mode!r} is not a boolean mode")
        if solver not in {"fast", "exact", "manifold"}:
            raise EngineError("engine.bad_boolean_solver", f"{solver!r} is not a solver")
        target = self._get(target_id)
        self._get(cutter_id)
        if mode == "union":
            self.join(target_id, [cutter_id])
        else:
            del self._objects[cutter_id]
            if mode == "intersect":
                target.faces = target.faces[: max(1, len(target.faces) // 2)]
        self._record("boolean", target_id, cutter_id, mode, solver)

    def solidify(self, object_id: str, thickness: float) -> None:
        obj = self._get(object_id)
        if thickness <= 0:
            raise EngineError("engine.bad_thickness", f"thickness {thickness} must be positive")
        offset = len(obj.vertices)
        obj.vertices.extend(v + Vec3(0, 0, thickness) for v in list(obj.vertices))
        obj.faces.extend(tuple(i + offset for i in f) for f in list(obj.faces))
        self._record("solidify", object_id, thickness)

    def array_along_curve(
        self,
        object_id: str,
        curve_points: Sequence[Vec3],
        spacing: float,
        *,
        keep_upright: bool,
        extra_points: Sequence[Vec3] = (),
        name_template: str = "{base}_i{index:03d}",
    ) -> list[str]:
        if spacing <= 0:
            raise EngineError("engine.bad_spacing", f"spacing {spacing} must be positive")
        if len(curve_points) < 2:
            raise EngineError(
                "engine.short_curve",
                "a curve needs at least two points",
                "pass the path's start and end at minimum",
            )
        positions = sample_polyline(curve_points, spacing)
        for p in extra_points:
            if all((p - q).length() > 1e-6 for q in positions):
                positions.append(p)
        positions.sort(key=lambda p: arc_length_to(curve_points, p))

        produced: list[str] = []
        for i, pos in enumerate(positions):
            rot = Quat.identity()
            if not keep_upright:
                rot = rotation_from_up_to(tangent_at(curve_points, pos))
            produced.append(
                self.duplicate(
                    object_id,
                    name_template.format(base=object_id, index=i),
                    Transform(translation=pos, rotation=rot),
                )
            )
        self._record("array_along_curve", object_id, len(produced), keep_upright)
        return produced

    def decimate(self, object_id: str, ratio: float) -> None:
        if not 0 < ratio <= 1:
            raise EngineError("engine.bad_ratio", f"ratio {ratio} must be in (0, 1]")
        obj = self._get(object_id)
        obj.faces = obj.faces[: max(1, int(len(obj.faces) * ratio))]
        self._record("decimate", object_id, ratio)

    def recalculate_normals(self, object_id: str, *, inside: bool = False) -> None:
        obj = self._get(object_id)
        if inside:
            obj.faces = [tuple(reversed(f)) for f in obj.faces]
        self._record("recalculate_normals", object_id, inside)

    def merge_by_distance(self, object_id: str, distance: float) -> RepairOutcome:
        obj = self._get(object_id)
        kept: list[Vec3] = []
        remap: dict[int, int] = {}
        for i, v in enumerate(obj.vertices):
            for j, k in enumerate(kept):
                if (v - k).length() <= distance:
                    remap[i] = j
                    break
            else:
                remap[i] = len(kept)
                kept.append(v)
        removed = len(obj.vertices) - len(kept)
        obj.vertices = kept
        deduped: list[tuple[int, ...]] = []
        degenerate = 0
        for f in obj.faces:
            nf = tuple(dict.fromkeys(remap[i] for i in f))
            if len(nf) >= 3:
                deduped.append(nf)
            else:
                degenerate += 1
        obj.faces = deduped
        self._record("merge_by_distance", object_id, distance, removed)
        return RepairOutcome(
            fixed=removed,
            skipped=degenerate,
            reason=f"{degenerate} face(s) collapsed below 3 vertices" if degenerate else "",
        )

    def fill_holes(self, object_id: str, max_sides: int = 0) -> RepairOutcome:
        obj = self._get(object_id)
        counts: dict[tuple[int, int], int] = {}
        for f in obj.faces:
            for a, b in zip(f, f[1:] + f[:1]):
                key = (min(a, b), max(a, b))
                counts[key] = counts.get(key, 0) + 1
        boundary = [e for e, n in counts.items() if n == 1]
        if not boundary:
            return RepairOutcome()
        filled = skipped = 0
        for loop in boundary_loops(boundary):
            if max_sides and len(loop) > max_sides:
                skipped += 1
                continue
            obj.faces.append(tuple(loop))
            filled += 1
        self._record("fill_holes", object_id, filled)
        return RepairOutcome(
            fixed=filled,
            skipped=skipped,
            reason=f"{skipped} hole(s) exceeded max_sides={max_sides}" if skipped else "",
        )

    # ---------------------------------------------------------------- lifecycle

    def reset(self) -> None:
        self._objects.clear()
        self._materials.clear()
        self._counter = 0
        self.calls.clear()
