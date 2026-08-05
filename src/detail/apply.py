"""Stub — running the heuristic edge treatment against a live object.

See ``src/detail/README.md``. Split from ``edges.py`` because this is the one function in
that pairing that mutates the engine (``contracts.ModifierOps.bevel_edges``) rather than
deciding something from a snapshot already in hand — a distinct actor, per
``.claude/rules/modularity.md``'s split-along-actor guidance.

Nothing here computes anything yet; the body raises until an implementer replaces it.
"""

from __future__ import annotations

from contracts import EngineProtocol

from .results import DetailResult

# Once implemented, this function calls detail.edges.select_bevel_edges and
# detail.edges.bevel_width_for — not imported yet because a throwing stub never calls them
# (see src/measure/report.py for the same pattern: its docstring names sibling functions by
# cross-reference without importing them until there is a body that actually calls them).

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

    Taking the write lock and logging this as a scene operation is deliberately **not** this
    function's job — there is no ``SceneDocument``/``WriteLease`` in this signature. This
    module depends only on ``contracts`` and ``measure`` (see ``.pipeline/modules.json``); the
    module that already owns the write lock and operation log applies that machinery around
    every call to this one.
    """
    raise NotImplementedError("detail.apply_edge_treatment: not implemented")
