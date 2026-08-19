"""``add_railing`` — the flagship operation this library exists for (ADR-004).

A railing is the user's own worked example of why typed, parametric operations sit between
primitives and whole-object composites: a raw-primitive agent needs ~140 calls to build one
and drift accumulates across every call; a single ``build("a railing")`` composite call
measures -12.6% Exec@1 because the model has to get a dozen parameters right at once with
no intermediate check (SheetCopilot, cited in ADR-004). This operation is the unit in
between — one call, four required named parameters, one re-runnable acceptance query.

Four things define a *correct* railing, and each is a documented naive-generator failure
mode this operation exists to prevent:

1. **Posts are plumb in world +Z, regardless of the path's slope.** Delegated to
   ``engine.array_along_curve(..., keep_upright=True)`` — the engine's own contract for
   ``keep_upright`` is exactly "each instance's own +Z parallel to world up", so every post
   stands vertical even on a 31-degree rake.
2. **Posts are additionally forced at every direction change**, via
   ``array_along_curve``'s ``extra_points`` — every interior path vertex, in addition to
   the regular pitch.
3. **The top rail terminates at post centrelines.** ``array_along_curve``'s own pacing
   always samples the path's first and last point exactly (see
   ``testing.mesh_helpers.sample_polyline``), so the first/last post sits exactly at
   ``path[0]``/``path[-1]`` — the rail is swept along that same ``path`` (elevated by
   ``height``), so its endpoints coincide with those same points by construction.
4. **Balusters are spaced to a clear opening, not a centre-to-centre pitch.** The
   centre-to-centre pitch handed to ``array_along_curve`` is computed as
   ``baluster_gap + baluster_size[0]`` — the gap plus the balusters' own footprint along
   the spacing axis — so the measured *surface* gap between neighbours comes out to
   exactly ``baluster_gap``.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult, Vec3

from ._defaults import resolve_dimensions
from ._geom import box_mesh
from ._rail_sweep import mitered_rectangular_sweep
from .validation import validate_params

__all__ = ["add_railing"]


def _array_source(
    engine: EngineProtocol, src_id: str, footprint: tuple[float, float], rise: float
) -> str:
    """A box source mesh spanning z in [0, rise], centred on x/y — so once
    ``array_along_curve`` translates a duplicate to a path point, that point is the
    instance's own base (walking-surface level), not its vertical centre."""
    w, d = footprint
    verts, faces = box_mesh(Vec3(-w / 2.0, -d / 2.0, 0.0), Vec3(w / 2.0, d / 2.0, rise))
    return engine.create_mesh(src_id, verts, faces)


def add_railing(engine: EngineProtocol, op: Operation) -> OperationResult:
    """A railing along ``path``: plumb posts at ``post_spacing`` (plus one at every
    corner), a top rail at ``height`` above the walking surface terminating at the outer
    posts' centrelines, and balusters plumb through slope changes holding ``baluster_gap``
    of clear opening between neighbours.

    See the module docstring for how each of the four defining properties maps onto
    ``engine.array_along_curve``. Returns ``produced_objects`` naming every part with an id
    predictable from ``op.op_id`` and its index:

    - posts: ``f"{op.op_id}_post_{i:03d}"``, arc-length order, corners included.
    - balusters: ``f"{op.op_id}_baluster_{i:03d}"``, same ordering convention.
    - top rail: ``f"{op.op_id}_top_rail"`` — exactly one, spanning the full path.

    The three cross-sections are optional and the only dimensions this library supplies on
    the caller's behalf. Every one it supplies comes back in
    :attr:`~contracts.OperationResult.assumptions`, so an agent that did not choose a post
    size can see the size it got and correct it (Gate B 1.4). The values themselves live in
    ``_defaults.py``, not in this call site.
    """
    params = validate_params("add_railing", op.params)
    path = list(params["path"])
    height = params["height"]
    post_spacing = params["post_spacing"]
    baluster_gap = params["baluster_gap"]

    dimensions, assumptions = resolve_dimensions("add_railing", params)
    post_w, post_d = dimensions["post_size"]
    bal_w, bal_d = dimensions["baluster_size"]
    rail_w, rail_d = dimensions["rail_size"]

    corners = list(path[1:-1])  # every direction change forces a post/baluster here too

    # -- posts: plumb, forced at corners, arc-length pitch -----------------------------
    post_src_id = _array_source(engine, f"{op.op_id}_post_src", (post_w, post_d), height)
    post_ids = engine.array_along_curve(
        post_src_id,
        path,
        post_spacing,
        keep_upright=True,
        extra_points=corners,
        name_template=f"{op.op_id}_post_{{index:03d}}",
    )
    engine.delete(post_src_id)

    # -- balusters: same pacing machinery, pitch derived from the CLEAR gap ------------
    baluster_pitch = baluster_gap + bal_w
    bal_src_id = _array_source(engine, f"{op.op_id}_baluster_src", (bal_w, bal_d), height)
    baluster_ids = engine.array_along_curve(
        bal_src_id,
        path,
        baluster_pitch,
        keep_upright=True,
        extra_points=corners,
        name_template=f"{op.op_id}_baluster_{{index:03d}}",
    )
    engine.delete(bal_src_id)

    # -- top rail: one continuous sweep with a shared miter ring at every bend ----------
    elevated = [p + Vec3(0.0, 0.0, height) for p in path]
    rail_name = f"{op.op_id}_top_rail"
    rail_verts, rail_faces = mitered_rectangular_sweep(elevated, rail_w, rail_d)
    rail_id = engine.create_mesh(rail_name, rail_verts, rail_faces)

    produced = tuple(post_ids) + tuple(baluster_ids) + (rail_id,)
    return OperationResult(
        op_id=op.op_id, ok=True, produced_objects=produced, assumptions=assumptions
    )
