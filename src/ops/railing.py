"""``add_railing`` — the flagship operation this library exists for (ADR-004).

A railing is the user's own worked example of why typed, parametric operations sit between
primitives and whole-object composites: a raw-primitive agent needs ~140 calls to build one
and drift accumulates across every call; a single ``build("a railing")`` composite call
measures -12.6% Exec@1 because the model has to get a dozen parameters right at once with
no intermediate check (SheetCopilot, cited in ADR-004). This operation is the unit in
between — one call, four required named parameters, one re-runnable acceptance query.

Four things define a *correct* railing, and each is a documented naive-generator failure
mode this operation exists to prevent:

1. **Posts are plumb in world +Z, regardless of the path's slope.** A post normal to a
   stair rake — aligned to the path tangent instead of world up — is *the* classic
   naive-generator error (``contracts.ConstraintKind.PLUMB``,
   ``testing.mesh_helpers.rotation_from_up_to``). Every post stands vertical even where the
   path it follows does not.
2. **Posts are additionally forced at every direction change**, not just at the fixed
   pitch. A regular spacing with no corner resampling leaves a corner either short a post
   (a gap) or straddled by two overlapping ones (a doubled post) — both invisible in a
   render, both a real defect.
3. **The top rail terminates at post centrelines**, not at an arbitrary parametric
   interval — a rail that stops short of or past the outer posts leaves either a stub with
   nothing to fix to, or a gap at the exact point someone is most likely to grab.
4. **Balusters are spaced to a clear opening, not a centre-to-centre pitch.** ``baluster_gap``
   names the gap a code-required sphere must not pass through — the surface-to-surface
   distance between neighbours, always narrower than their centre-to-centre pitch by the
   balusters' own width. Confusing the two is a real, common modelling bug.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_railing"]

_NOT_IMPLEMENTED = "ops.{name}: not implemented"


def add_railing(engine: EngineProtocol, op: Operation) -> OperationResult:
    """A railing along ``path``: plumb posts at ``post_spacing`` (plus one at every
    corner), a top rail at ``height`` above the walking surface terminating at the outer
    posts' centrelines, and balusters plumb through slope changes holding ``baluster_gap``
    of clear opening between neighbours.

    Required params:

    - ``object_id`` (str) — base id every produced part's name is derived from.
    - ``path`` (list of >= 2 ``Vec3``) — the walking surface's outer edge, in order. A
      vertex where the direction changes is a corner and must receive a post regardless of
      where the regular pitch would otherwise fall.
    - ``height`` (float, > 0) — top rail height above the walking surface (i.e. above
      ``path``'s own z at each point, not a fixed world z — the rail rises and falls with
      the path).
    - ``post_spacing`` (float, > 0) — nominal pitch between posts, measured along the
      path's own arc length, never along its horizontal projection. On a rake this is a
      materially larger number than the horizontal run, and using the wrong one under-
      counts posts.
    - ``baluster_gap`` (float, > 0) — the required *clear* opening between adjacent
      baluster surfaces. Not the same number as the centre-to-centre pitch, which is wider
      by the balusters' own width (``baluster_size``).

    Optional: ``post_size`` ((width, depth), default ``(0.05, 0.05)``), ``baluster_size``
    (default ``(0.03, 0.03)``), ``rail_size`` (default ``(0.05, 0.05)``).

    Must call ``validate_params("add_railing", op.params)`` first.

    Every post's local +Z, transformed by its own placed rotation, must equal world +Z —
    checked directly on ``engine.snapshot(post_id).transform``, on a level path and on a
    sloped one alike. This is the one property that must never regress: it is the exact
    thing ADR-004 names as the reason this operation exists rather than a raw
    ``array_along_curve`` call with ``keep_upright`` left to the caller to remember.

    Returns ``produced_objects`` naming every part with an id predictable from ``op.op_id``
    and its index, so a later constraint can reference one baluster without re-deriving
    which array position it was:

    - posts: ``f"{op.op_id}_post_{i:03d}"``, ``i`` in path order (arc-length order,
      corners included), zero-padded to 3 digits.
    - balusters: ``f"{op.op_id}_baluster_{i:03d}"``, same ordering convention.
    - top rail: ``f"{op.op_id}_top_rail"`` — exactly one, spanning the full path.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_railing"))
