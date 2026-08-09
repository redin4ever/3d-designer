"""Converting ``contracts.MeshSnapshot``/``contracts.Transform`` into the wire payloads
``contracts.wire`` defines (ADR-011).

Two conversions, and each exists because getting it wrong is invisible until it is not:
flat buffers instead of nested per-vertex objects (what keeps a thousands-of-objects scene
responsive), and quaternion component order (three.js is x,y,z,w; ``contracts.Quat`` is
stored w-first).

Nothing here is implemented yet (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import MeshPayload, MeshSnapshot, TransformPayload

__all__ = ["snapshot_to_payload", "transform_payload"]


def snapshot_to_payload(snap: MeshSnapshot) -> MeshPayload:
    """Flatten one ``MeshSnapshot`` into typed-array-friendly buffers.

    Once implemented: ``positions`` is ``[v0.x, v0.y, v0.z, v1.x, ...]`` — length
    ``3 * snap.vertex_count`` — and ``indices`` is the triangles flattened the same way —
    length ``3 * snap.triangle_count``. Deliberately flat rather than a list of per-vertex
    objects: that is what maps straight onto a ``BufferGeometry`` attribute with no
    per-vertex churn in the browser (``MeshPayload``'s own docstring, ADR-011).

    ``materials`` carries every slot in ``snap.material_slots``, not just the first — a
    mesh with several materials cannot be rendered faithfully from one name
    (``MeshPayload.materials``'s own docstring). ``groups`` is the matching
    ``(start, count, material_index)`` draw ranges derived from
    ``snap.triangle_materials``, empty when there is at most one slot.
    """
    positions: list[float] = []
    for v in snap.vertices:
        positions.extend((float(v.x), float(v.y), float(v.z)))

    indices: list[int] = []
    for tri in snap.triangles:
        indices.extend(int(i) for i in tri)

    normals: list[float] | None = None
    if snap.normals is not None:
        normals = []
        for n in snap.normals:
            normals.extend((float(n.x), float(n.y), float(n.z)))

    uvs: list[float] | None = None
    if snap.uvs is not None:
        uvs = []
        for u, v in snap.uvs:
            uvs.extend((float(u), float(v)))

    return MeshPayload(
        object_id=snap.object_id,
        positions=positions,
        indices=indices,
        normals=normals,
        uvs=uvs,
        materials=tuple(snap.material_slots),
        material_definitions=dict(snap.material_definitions),
        groups=_material_groups(snap),
        triangle_count=snap.triangle_count,
    )


def _material_groups(snap: MeshSnapshot) -> tuple[tuple[int, int, int], ...]:
    """(start, count, material_index) draw ranges over the flattened indices, one per
    contiguous run of a single material in triangle order.

    Empty when there is at most one material slot -- MeshPayload.groups's own docstring:
    "empty means the whole mesh uses materials[0]". A mesh with more than one slot but no
    triangle_materials is already rejected by MeshSnapshot.__post_init__ ("the viewer
    cannot split it and would drop all but one"), so this never has to guess which
    triangle belongs to which slot.
    """
    materials = snap.triangle_materials
    if not materials:
        return ()
    groups: list[tuple[int, int, int]] = []
    run_start = 0
    run_material = materials[0]
    total = len(materials)
    for i in range(1, total + 1):
        if i == total or materials[i] != run_material:
            groups.append((run_start * 3, (i - run_start) * 3, run_material))
            if i < total:
                run_start = i
                run_material = materials[i]
    return tuple(groups)


def transform_payload(snap: MeshSnapshot) -> TransformPayload:
    """Convert ``snap.transform`` once, at the boundary, into three.js's x,y,z,w
    quaternion order.

    Once implemented: ``contracts.Quat`` is stored w-first internally (``Quat``'s own
    docstring); this method is the one place that reorders to ``(x, y, z, w)``. Getting
    the order wrong here is invisible until something spins wrongly on screen
    (``TransformPayload.quaternion``'s own docstring) — the whole reason this conversion
    happens exactly once, at this boundary, rather than being reimplemented per caller.
    """
    t = snap.transform
    q = t.rotation
    return TransformPayload(
        object_id=snap.object_id,
        position=t.translation.as_tuple(),
        quaternion=(q.x, q.y, q.z, q.w),
        scale=t.scale.as_tuple(),
    )
