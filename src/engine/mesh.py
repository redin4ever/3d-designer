"""``MeshOps`` — mesh creation, editing and inspection against bpy's data API.

Every method below prefers ``bpy.data``/``bmesh`` over ``bpy.ops`` (ADR-001) — object
creation, transforms, joining and separation are all plain data manipulation with no
operator involved. See ``src/engine/_shared.py`` for the two invariants (always-triangulated
storage; UV-split snapshot topology) this file and ``modifiers.py``/``surfacing.py`` share.
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, EngineError, MeshSnapshot, Transform, Vec3

from ._shared import (
    apply_transform_fields,
    build_snapshot_topology,
    delete_object,
    get_object,
    link_new_object,
    read_transform_fields,
    world_bounds_of,
    write_bmesh,
)
from .primitives import build_primitive_bmesh

__all__ = ["MeshOpsMixin"]


class MeshOpsMixin:
    """``MeshOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def create_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
        transform: Transform | None = None,
    ) -> str:
        import bmesh
        import bpy

        if not vertices:
            raise EngineError("engine.empty_mesh", "a mesh needs at least one vertex")

        mesh = bpy.data.meshes.new(f"{object_id}_mesh")
        mesh.from_pydata([v.as_tuple() for v in vertices], [], [list(f) for f in faces])
        mesh.update()

        obj = link_new_object(object_id, mesh)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        write_bmesh(bm, obj)
        apply_transform_fields(obj, transform or Transform())
        return obj.name

    def create_primitive(
        self, object_id: str, kind: str, size: Vec3, transform: Transform | None = None
    ) -> str:
        import bpy

        bm = build_primitive_bmesh(kind, size)  # raises engine.unknown_primitive
        mesh = bpy.data.meshes.new(f"{object_id}_mesh")
        obj = link_new_object(object_id, mesh)
        write_bmesh(bm, obj)
        apply_transform_fields(obj, transform or Transform())
        return obj.name

    def duplicate(self, object_id: str, new_id: str, transform: Transform | None = None) -> str:
        src = get_object(object_id)
        new_mesh = src.data.copy()
        new_obj = link_new_object(new_id, new_mesh)
        apply_transform_fields(new_obj, transform if transform is not None else read_transform_fields(src))
        return new_obj.name

    def delete(self, object_id: str) -> None:
        delete_object(get_object(object_id))

    def set_transform(self, object_id: str, transform: Transform) -> None:
        apply_transform_fields(get_object(object_id), transform)

    def apply_transform(
        self, object_id: str, *, location: bool, rotation: bool, scale: bool
    ) -> None:
        import bmesh
        from mathutils import Matrix

        obj = get_object(object_id)
        loc, rot, scl = obj.location.copy(), obj.rotation_quaternion.copy(), obj.scale.copy()

        matrix = Matrix.Identity(4)
        if scale:
            matrix = Matrix.Diagonal((scl.x, scl.y, scl.z, 1.0)) @ matrix
        if rotation:
            matrix = rot.to_matrix().to_4x4() @ matrix
        if location:
            matrix = Matrix.Translation(loc) @ matrix

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts[:])
        write_bmesh(bm, obj)

        obj.location = (0.0, 0.0, 0.0) if location else (loc.x, loc.y, loc.z)
        obj.rotation_quaternion = (1.0, 0.0, 0.0, 0.0) if rotation else (rot.w, rot.x, rot.y, rot.z)
        obj.scale = (1.0, 1.0, 1.0) if scale else (scl.x, scl.y, scl.z)

    def join(self, target_id: str, source_ids: Sequence[str]) -> str:
        import bmesh

        target = get_object(target_id)
        bm = bmesh.new()
        bm.from_mesh(target.data)

        for sid in source_ids:
            src = get_object(sid)
            new_verts = []
            for v in src.data.vertices:
                world = src.matrix_world @ v.co
                local = target.matrix_world.inverted() @ world
                new_verts.append(bm.verts.new(local))
            bm.verts.ensure_lookup_table()
            for poly in src.data.polygons:
                try:
                    bm.faces.new([new_verts[i] for i in poly.vertices])
                except ValueError:
                    pass  # duplicate face — harmless, skip
            delete_object(src)

        write_bmesh(bm, target)
        return target.name

    def separate_loose(self, object_id: str) -> list[str]:
        obj = get_object(object_id)
        mesh = obj.data
        n = len(mesh.vertices)
        adjacency: list[set] = [set() for _ in range(n)]
        for poly in mesh.polygons:
            verts = list(poly.vertices)
            for a in verts:
                adjacency[a].update(verts)

        seen: set = set()
        components: list[set] = []
        for start in range(n):
            if start in seen:
                continue
            stack, comp = [start], set()
            while stack:
                v = stack.pop()
                if v in comp:
                    continue
                comp.add(v)
                stack.extend(adjacency[v] - comp)
            seen |= comp
            components.append(comp)

        if len(components) <= 1:
            return [object_id]

        transform = read_transform_fields(obj)
        produced = []
        for idx, comp in enumerate(components):
            remap = {old: new for new, old in enumerate(sorted(comp))}
            verts = [Vec3(*mesh.vertices[o].co) for o in sorted(comp)]
            faces = [
                tuple(remap[i] for i in poly.vertices)
                for poly in mesh.polygons
                if set(poly.vertices) <= comp
            ]
            produced.append(self.create_mesh(f"{object_id}_part{idx}", verts, faces, transform))
        delete_object(obj)
        return produced

    def snapshot(self, object_id: str) -> MeshSnapshot:
        obj = get_object(object_id)
        mesh = obj.data
        vertices, triangles, uvs, _ = build_snapshot_topology(mesh)

        material_slots = tuple(m.name if m is not None else "" for m in mesh.materials)
        triangle_materials = None
        if len(material_slots) > 1:
            triangle_materials = [poly.material_index for poly in mesh.polygons]

        if triangle_materials is not None and len(triangle_materials) != len(triangles):
            # A polygon that fan-triangulates into N triangles needs its material index
            # repeated N times, or the per-triangle array no longer lines up with the
            # triangle list and the contract rejects the snapshot.
            triangle_materials = [
                poly.material_index
                for poly in mesh.polygons
                for _ in range(max(1, poly.loop_total - 2))
            ]

        return MeshSnapshot(
            object_id=obj.name,
            vertices=vertices,
            triangles=triangles,
            transform=read_transform_fields(obj),
            uvs=uvs,
            polygon_count=len(mesh.polygons),
            material_slots=material_slots,
            triangle_materials=triangle_materials,
        )

    def list_objects(self) -> list[str]:
        import bpy

        return sorted(o.name for o in bpy.data.objects if o.type == "MESH")

    def exists(self, object_id: str) -> bool:
        import bpy

        obj = bpy.data.objects.get(object_id)
        return obj is not None and obj.type == "MESH"

    def world_bounds(self, object_id: str) -> AABB:
        return world_bounds_of(get_object(object_id))
