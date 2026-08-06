"""``cleanup_bevel_topology`` — running the planar re-triangulation against a live object.

Split from ``topology.py`` because this is the one function in the pairing that *mutates* the
engine, the same actor seam ``apply.py``/``edges.py`` already uses (Rule 2). The decision —
which triangles — is made there, from a snapshot already in hand; all that happens here is
writing it back and refusing to write it back when something would be lost.

**Why it rebuilds the mesh rather than editing it.** ``EngineProtocol`` has no "replace this
object's triangles" method, and adding one would be a contract change in a frozen surface
(Rule 5). Delete-then-``create_mesh`` under the same id is the only route the protocol
offers, and it works identically on ``FakeEngine`` and on real Blender, which is what lets
the decision above be tested without Blender at all. What it costs is anything the mesh
carries that ``MeshOps.create_mesh`` does not take — a UV layer, per-triangle material
assignment — and rather than lose those silently this pass declines and says so (Gate A 4.2).
"""

from __future__ import annotations

from contracts import EngineError, EngineProtocol, MeshSnapshot

from .quality import mean_triangle_aspect_ratio
from .results import DetailResult
from .topology import retriangulate_planar_regions

__all__ = ["cleanup_bevel_topology"]


def cleanup_bevel_topology(
    engine: EngineProtocol, object_id: str, *, coplanar_tolerance_deg: float = 0.5
) -> DetailResult:
    """Re-triangulate ``object_id`` in place, moving no vertex.

    This is the F-018 fix, and it is its own step rather than part of ``bevel_edges`` on
    purpose: it is measurable in isolation, skippable (``apply_edge_treatment(cleanup=False)``
    — which is how ``bevel_quality_test.py`` measures the defect it removes), and re-runnable
    on a mesh somebody else bevelled.

    It reports ``changed=False``, with the reason, when:

    - the object carries a UV layer — rebuilding drops it, and a silently unwrapped object
      costs a bake; run the edge treatment before unwrapping instead;
    - the object has more than one material slot — per-triangle material assignment cannot
      survive ``MeshOps.create_mesh``, and flattening it would be a visible silent regression;
    - nothing measured better than the triangulation already there.

    Anything the engine raises — ``engine.unknown_object`` in particular, which already names
    what does exist — propagates unchanged. Wrapping it would replace a message an agent can
    act on with one it cannot.
    """
    snapshot = engine.snapshot(object_id)
    triangles_before = snapshot.triangle_count

    refusal = _refusal(snapshot)
    if refusal:
        return DetailResult(
            object_id=object_id,
            changed=False,
            triangles_before=triangles_before,
            triangles_after=triangles_before,
            detail=refusal,
        )

    triangles = retriangulate_planar_regions(
        snapshot, coplanar_tolerance_deg=coplanar_tolerance_deg
    )
    if _same_triangles(triangles, snapshot.triangles):
        return DetailResult(
            object_id=object_id,
            changed=False,
            triangles_before=triangles_before,
            triangles_after=triangles_before,
            detail="no planar region measured better than the triangulation it already had",
        )

    before_ratio = mean_triangle_aspect_ratio(snapshot)
    _rebuild(engine, snapshot, triangles)

    after = engine.snapshot(object_id)
    return DetailResult(
        object_id=object_id,
        changed=True,
        triangles_before=triangles_before,
        triangles_after=after.triangle_count,
        detail=(
            "re-triangulated flat regions in place (no vertex moved): mean triangle aspect "
            f"ratio {before_ratio:.1f} -> {mean_triangle_aspect_ratio(after):.1f}"
        ),
    )


def _refusal(snapshot: MeshSnapshot) -> str:
    """Why this object must not be rebuilt, or ``""`` when it may be."""
    if snapshot.uvs is not None:
        return (
            "declined: this object has a UV layer, and rebuilding the mesh would drop it — "
            "run the edge treatment and its cleanup before unwrapping, not after"
        )
    if len(snapshot.material_slots) > 1:
        return (
            f"declined: this object has {len(snapshot.material_slots)} material slots and "
            "per-triangle material assignment cannot survive a mesh rebuild — split it by "
            "material first, or accept the current triangulation"
        )
    return ""


def _same_triangles(candidate, current) -> bool:
    """Whether two triangle lists describe the same surface.

    Compared as an order-insensitive multiset of unordered index triples: a region that
    measured no better is emitted with its own triangles, but grouping by region can permute
    the list as a whole. Comparing the lists directly would report that permutation as a
    change and turn an honest no-op into a mesh rebuild on every replay.
    """
    return sorted(tuple(sorted(t)) for t in candidate) == sorted(
        tuple(sorted(t)) for t in current
    )


def _rebuild(engine: EngineProtocol, snapshot: MeshSnapshot, triangles) -> None:
    """Replace the object's mesh with ``triangles`` over its own, unchanged vertices."""
    object_id = snapshot.object_id
    materials = tuple(snapshot.material_slots)

    engine.delete(object_id)
    rebuilt = engine.create_mesh(
        object_id, list(snapshot.vertices), list(triangles), snapshot.transform
    )
    if rebuilt != object_id:
        raise EngineError(
            "detail.rebuild_renamed",
            f"re-creating {object_id!r} produced {rebuilt!r} instead — the name was taken "
            "between the delete and the create",
            "nothing else may create objects while a detail pass holds the write lock; "
            f"rename {rebuilt!r} back to {object_id!r} to recover",
        )
    for slot, material_id in enumerate(materials):
        if material_id:
            engine.assign_material(object_id, material_id, slot)
