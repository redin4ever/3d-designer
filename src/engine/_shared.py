"""Internal bpy plumbing shared by every ``Ops`` mixin.

Not a mixin itself and not merged into :class:`~engine.session.BlenderEngine` — a plain
module of helper functions the five mixins (``mesh.py``, ``modifiers.py``, ``surfacing.py``,
``exporting.py``) import. Kept separate so each mixin file stays focused on its own
``Ops`` surface (Rule 2 seam #1: a distinct decision — bpy/contracts plumbing — rather than
a distinct actor).

Every function here imports ``bpy``/``bmesh``/``mathutils`` **locally**, not at module level,
so that ``import engine`` keeps succeeding on a machine with no Blender installed (only a
method *call* ever touches bpy) — see ``src/engine/README.md`` on why collection must never
fail with ``ImportError``.

Two invariants everything else in this package relies on:

1. **Every object's stored mesh is always fully triangulated.** ``write_bmesh`` re-triangulates
   before every write-back. This is what makes an ``edge_indices`` list computed from a prior
   ``MeshSnapshot.edges()`` call resolvable back to a *real* bmesh edge later — without it, a
   quad's un-materialised diagonal would be a canonical "edge" with no bmesh edge behind it.
2. **``MeshSnapshot`` vertices may be split from the mesh's real vertices** when a UV layer is
   present (Blender stores UVs per face-corner). ``build_snapshot_topology`` returns the
   split-vertex-index -> original-vertex-index mapping precisely so ``bevel_edges`` and
   ``mark_seams`` can translate a caller's ``edge_indices`` (which index into the *split*
   numbering whenever the object has been unwrapped) back to the real mesh edge.
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, EngineError, Quat, Transform, Vec3

__all__ = [
    "get_object",
    "get_material",
    "delete_object",
    "link_new_object",
    "apply_transform_fields",
    "read_transform_fields",
    "world_bounds_of",
    "write_bmesh",
    "build_snapshot_topology",
    "canonical_edges",
    "edge_lookup_by_original_vertices",
    "apply_modifier_result",
]


def get_object(object_id: str):
    """Look up a live mesh object, or raise ``engine.unknown_object`` naming what exists."""
    import bpy

    obj = bpy.data.objects.get(object_id)
    if obj is None or obj.type != "MESH":
        known = sorted(o.name for o in bpy.data.objects if o.type == "MESH")
        raise EngineError(
            rule="engine.unknown_object",
            detail=f"no object named {object_id!r}",
            suggestion=f"known objects: {', '.join(known) or '(none)'}",
        )
    return obj


def get_material(material_id: str):
    """Look up a live material, or raise ``engine.unknown_material`` naming what exists."""
    import bpy

    mat = bpy.data.materials.get(material_id)
    if mat is None:
        known = sorted(m.name for m in bpy.data.materials)
        raise EngineError(
            rule="engine.unknown_material",
            detail=f"no material named {material_id!r}",
            suggestion=f"known materials: {', '.join(known) or '(none)'}",
        )
    return mat


def delete_object(obj) -> None:
    """Remove an object and, if nothing else references it, its mesh datablock too."""
    import bpy

    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def link_new_object(name: str, mesh) -> object:
    """Create an object for ``mesh``, link it into the scene, and set up quaternion rotation.

    Returns the object with its **actual** (possibly collision-renamed) name — bpy
    auto-uniquifies on creation, which is exactly the "renamed, not overwritten" behaviour
    ``MeshOps.create_mesh`` et al. promise.
    """
    import bpy

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    return obj


def apply_transform_fields(obj, transform: Transform) -> None:
    """Write ``transform`` onto ``obj`` and force ``matrix_world`` to reflect it immediately.

    Setting ``obj.location``/``rotation_quaternion``/``scale`` updates ``matrix_basis``
    synchronously but leaves ``matrix_world`` stale until the view layer re-evaluates —
    verified empirically: reading ``obj.matrix_world`` right after a location assignment
    still returns the pre-assignment value. Every caller of this function (``create_mesh``,
    ``duplicate``, ``set_transform``, and transitively every modifier operation that reads a
    just-moved object's world position, e.g. ``boolean``'s cutter) needs ``matrix_world``
    correct the instant this returns, so the refresh belongs here once rather than repeated
    at every call site.
    """
    import mathutils

    obj.rotation_mode = "QUATERNION"
    obj.location = (transform.translation.x, transform.translation.y, transform.translation.z)
    obj.rotation_quaternion = (
        transform.rotation.w, transform.rotation.x, transform.rotation.y, transform.rotation.z,
    )
    obj.scale = (transform.scale.x, transform.scale.y, transform.scale.z)

    # Compose matrix_world ourselves rather than asking the view layer to re-evaluate.
    #
    # `bpy.context.view_layer.update()` re-evaluates the whole dependency graph, so calling
    # it once per object made object creation O(scene) each time and O(n^2) overall:
    # measured 3.16 ms/op at ~100 objects rising to 54.52 ms/op at ~900, a 17x degradation
    # against a stated target of thousands. For an unparented object `matrix_world` is just
    # its own loc/rot/scale composition, so this is exact and costs nothing.
    #
    # A parented object still needs the parent's matrix, which only the graph knows — those
    # fall back to the old path. Nothing in this product parents objects today, so the
    # fallback is unreached, but silently producing a wrong world matrix for one would be
    # far worse than being slow.
    if obj.parent is None:
        obj.matrix_world = mathutils.Matrix.LocRotScale(
            mathutils.Vector(obj.location),
            mathutils.Quaternion(obj.rotation_quaternion),
            mathutils.Vector(obj.scale),
        )
    else:
        import bpy

        bpy.context.view_layer.update()


def read_transform_fields(obj) -> Transform:
    obj.rotation_mode = "QUATERNION"
    loc, rot, scl = obj.location, obj.rotation_quaternion, obj.scale
    return Transform(
        translation=Vec3(loc.x, loc.y, loc.z),
        rotation=Quat(rot.w, rot.x, rot.y, rot.z),
        scale=Vec3(scl.x, scl.y, scl.z),
    )


def world_bounds_of(obj) -> AABB:
    world = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return AABB.from_points([Vec3(p.x, p.y, p.z) for p in world])


def write_bmesh(bm, obj) -> None:
    """Re-triangulate (invariant #1) and flush a bmesh back into ``obj``'s mesh datablock."""
    import bmesh

    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="EAR_CLIP")
    bm.normal_update()
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def build_snapshot_topology(mesh):
    """Return ``(vertices, triangles, uvs, orig_of)`` for ``MeshSnapshot`` (invariant #2).

    ``orig_of[i]`` is the original ``mesh.vertices`` index the ``i``-th output vertex was
    split from. When the mesh has no active UV layer, output vertices are exactly the mesh's
    own vertices (``orig_of[i] == i``) and ``uvs`` is ``None``.
    """
    uv_layer = mesh.uv_layers.active
    has_uv = uv_layer is not None and len(uv_layer.data) > 0

    key_to_new: dict = {}
    vertices: list[Vec3] = []
    uvs: list[tuple[float, float]] | None = [] if has_uv else None
    orig_of: list[int] = []
    triangles: list[tuple[int, int, int]] = []

    for poly in mesh.polygons:
        corners = []
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            orig_idx = mesh.loops[li].vertex_index
            if has_uv:
                uv = tuple(uv_layer.data[li].uv)
                key = (orig_idx, round(uv[0], 6), round(uv[1], 6))
            else:
                key = orig_idx
            new_idx = key_to_new.get(key)
            if new_idx is None:
                new_idx = len(vertices)
                key_to_new[key] = new_idx
                co = mesh.vertices[orig_idx].co
                vertices.append(Vec3(co.x, co.y, co.z))
                orig_of.append(orig_idx)
                if has_uv:
                    uvs.append(uv)
            corners.append(new_idx)

        # Fan-triangulate. Geometry this engine creates is already triangles, but a mesh
        # it did not create is not — Blender's own startup cube is quads, and so is every
        # imported asset and every hand-modelled .blend. Assuming triangles made
        # `snapshot()` raise on the first mesh from outside, which meant `measure` could
        # not inspect any of them: the exact geometry a user most wants checked.
        #
        # A fan is correct for convex polygons, which Blender quads overwhelmingly are.
        # `polygon_count` below preserves the pre-triangulation face count, because
        # polygon budgets and topology quality are stated in faces, not triangles.
        for i in range(1, len(corners) - 1):
            triangles.append((corners[0], corners[i], corners[i + 1]))

    # Carry vertices that no face references. Walking only `mesh.polygons` dropped them
    # entirely, which made `measure.find_loose_or_duplicate`'s loose-vertex detection dead
    # code against real Blender while working correctly against the fake — the detector
    # could never see the thing it exists to find. A loose vertex is a real defect: it
    # bloats the mesh, survives export, and is invisible in a viewport.
    referenced = set(orig_of)
    for orig_idx in range(len(mesh.vertices)):
        if orig_idx in referenced:
            continue
        co = mesh.vertices[orig_idx].co
        vertices.append(Vec3(co.x, co.y, co.z))
        orig_of.append(orig_idx)
        if has_uv:
            uvs.append((0.0, 0.0))

    return vertices, triangles, uvs, orig_of


def canonical_edges(triangles: Sequence[tuple[int, int, int]]) -> list[tuple[int, int]]:
    """The exact algorithm ``MeshSnapshot.edges()`` uses, over an arbitrary triangle list.

    Kept in lock-step with ``contracts.geometry.MeshSnapshot.edges()`` on purpose: this is
    what lets ``bevel_edges``/``mark_seams`` resolve a caller's ``edge_indices`` — computed
    from a prior ``snapshot(...).edges()`` call — back to real geometry.
    """
    seen: dict[tuple[int, int], None] = {}
    for tri in triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            seen.setdefault((a, b) if a < b else (b, a), None)
    return list(seen)


def edge_lookup_by_original_vertices(edges) -> dict:
    """``{frozenset({vert_a, vert_b}): edge}`` for a flat iterable of edges with ``.vertices``
    or ``.verts`` (works for both raw ``bpy`` mesh edges and bmesh edges)."""
    lookup = {}
    for e in edges:
        idx = e.vertices if hasattr(e, "vertices") else (e.verts[0].index, e.verts[1].index)
        lookup[frozenset((idx[0], idx[1]))] = e
    return lookup


def apply_modifier_result(obj, modifier) -> None:
    """Evaluate ``modifier`` via the depsgraph, bake the result into ``obj``'s mesh data, and
    remove the modifier — every ``ModifierOps`` mutation is destructive and immediate
    (``ModifierOps`` docstring), so no modifier ever lingers on the stack afterwards."""
    import bmesh
    import bpy

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(evaluated)
    old_mesh = obj.data
    obj.modifiers.remove(modifier)
    obj.data = new_mesh
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    write_bmesh(bm, obj)
