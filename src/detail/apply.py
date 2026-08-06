"""Stub — running the heuristic edge treatment against a live object.

See ``src/detail/README.md``. Split from ``edges.py`` because this is the one function in
that pairing that mutates the engine (``contracts.ModifierOps.bevel_edges``) rather than
deciding something from a snapshot already in hand — a distinct actor, per
``.claude/rules/modularity.md``'s split-along-actor guidance.

Nothing here computes anything yet; the body raises until an implementer replaces it.
"""

from __future__ import annotations

from contracts import EngineProtocol

from .cleanup import cleanup_bevel_topology
from .edges import EdgeSelection, bevel_width_for, select_bevel_edges
from .results import DetailResult

__all__ = ["apply_edge_treatment"]


def apply_edge_treatment(
    engine: EngineProtocol,
    object_id: str,
    *,
    segments: int = 2,
    min_dihedral_deg: float = 30.0,
    convex_only: bool = True,
    exclude_hidden: bool = True,
    fraction: float = 0.004,
    minimum: float = 0.0005,
    maximum: float = 0.01,
    cleanup: bool = True,
) -> DetailResult:
    """Select edges on ``object_id`` and bevel exactly those, in one call.

    Once implemented, this function must:

    - Take ``engine.snapshot(object_id)``, run :func:`detail.select_bevel_edges` over it with
      ``min_dihedral_deg``/``convex_only``/``exclude_hidden``, and compute a width with
      :func:`detail.bevel_width_for` using ``fraction``/``minimum``/``maximum`` — never a
      width chosen independently of the object's own size.
    - When the selection is empty (nothing on this object qualifies), return
      ``DetailResult(changed=False, ...)`` with ``triangles_before == triangles_after``
      **without** calling ``engine.bevel_edges`` at all. A no-op that still reports
      ``changed=True`` is indistinguishable from a real pass to anything reading the result,
      which is exactly the false-success shape Gate A 4.1/4.2 exist to rule out.
    - Otherwise call ``engine.bevel_edges(object_id, width, segments, selection.edge_indices)``
      and let whatever it raises — in particular ``EngineError`` when the object has
      unapplied non-uniform scale, since bevel width is computed in object space and an
      unapplied scale would silently produce an uneven bevel — **propagate to the caller
      unchanged**. Catching it here and returning a "soft" failure would hide the one error
      class this whole pass depends on the engine to catch; see
      ``apply_test.py::test_unapplied_scale_surfaces_as_an_engine_error``.
    - Record ``triangles_before``/``triangles_after`` from real ``engine.snapshot(object_id)``
      calls bracketing the mutation, not from arithmetic derived from the selection — the
      engine is the only source of truth for how many triangles a bevel actually produced.

    ``cleanup`` (default ``True``) runs :func:`detail.cleanup_bevel_topology` immediately
    after the bevel. That is the F-018 fix and it is on by default because an opt-in quality
    pass is one an unattended agent never opts into: a real Blender bevel leaves the flat
    faces around it ear-clipped into needles measuring 1378:1, and the mean triangle aspect
    ratio on a stair tread drops from ~109 to ~64 when this runs. Pass ``cleanup=False`` to
    measure the bevel in isolation or to keep the engine's own triangulation exactly as it
    came out. A bevel that did nothing never runs a cleanup either — there are no bevel
    slivers to clean up, and rebuilding the mesh would turn a documented no-op into a real
    mutation.

    Taking the write lock and logging this as a scene operation is deliberately **not** this
    function's job — there is no ``SceneDocument``/``WriteLease`` in this signature. This
    module depends only on ``contracts`` and ``measure`` (see ``.pipeline/modules.json``); the
    module that already owns the write lock and operation log applies that machinery around
    every call to this one.
    """
    snapshot = engine.snapshot(object_id)
    triangles_before = snapshot.triangle_count

    selection = select_bevel_edges(
        snapshot,
        min_dihedral_deg=min_dihedral_deg,
        convex_only=convex_only,
        exclude_hidden=exclude_hidden,
    )

    if not selection.edge_indices:
        return DetailResult(
            object_id=object_id,
            changed=False,
            triangles_before=triangles_before,
            triangles_after=triangles_before,
            detail="no edge qualified for a bevel — nothing exposed, convex and sharp enough",
        )

    width = bevel_width_for(snapshot, fraction=fraction, minimum=minimum, maximum=maximum)

    # Deliberately not caught: an EngineError here (e.g. unapplied non-uniform scale) must
    # reach the caller unchanged — see this function's docstring and apply_test.py.
    engine.bevel_edges(object_id, width, segments, selection.edge_indices)

    detail = (
        f"bevelled {_stated_reasoning(selection, len(snapshot.edges()), min_dihedral_deg)} "
        f"at width={width:.5f}m, {segments} segment(s)"
    )
    if cleanup:
        detail += f"; cleanup: {cleanup_bevel_topology(engine, object_id).detail}"

    triangles_after = engine.snapshot(object_id).triangle_count
    return DetailResult(
        object_id=object_id,
        changed=True,
        triangles_before=triangles_before,
        triangles_after=triangles_after,
        detail=detail,
    )


def _stated_reasoning(
    selection: EdgeSelection, edge_count: int, min_dihedral_deg: float
) -> str:
    """"8 of 18 edges, because they are convex and exposed and fold by at least 30 degrees".

    The heuristic already records why each edge qualified; saying so is what makes an agent's
    next call better than a guess. A tool that reports only a count leaves the agent with no
    way to tell "nothing qualified" from "the threshold was wrong", which is the difference
    between accepting the result and re-running it with ``min_dihedral_deg`` lowered — and
    the rejected count is what tells it which of those two it is looking at.
    """
    chosen = len(selection.edge_indices)
    # Every entry in `reasons` names the same set of filters (they are the ones that were
    # enabled), so the shared phrase is one line, not one per edge. Per-edge angles are in
    # `EdgeSelection.reasons` for a caller that wants them.
    qualities = sorted(
        {tag for reason in selection.reasons for tag in reason.split() if "=" not in tag}
    )
    qualities.append(f"fold by at least {min_dihedral_deg:g} degrees")
    return (
        f"{chosen} of {edge_count} edges, because they are {' and '.join(qualities)} "
        f"({selection.rejected} other candidate(s) considered and rejected)"
    )
