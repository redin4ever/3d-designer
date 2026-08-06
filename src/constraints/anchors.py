"""Anchor resolution — turning a symbolic reference into world geometry.

An ``Anchor`` (``src/contracts/constraints.py``) names a target *symbolically*:
``stair_01.outer_edge``, never a resolved coordinate. That is the entire mechanism behind
live re-solve (ADR-002) — the stair moves, the anchor's identity survives, and the next
resolve call reads the new geometry. Anything that resolves an anchor once and caches the
number defeats the reason anchors are symbolic in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import EPSILON, Anchor, AnchorKind, EngineProtocol, Vec3, WORLD_UP

from .errors import ConstraintRuleError

__all__ = ["AnchorResolution", "resolve_anchor"]


@dataclass(frozen=True, slots=True)
class AnchorResolution:
    """The concrete geometry an :class:`~contracts.Anchor` resolves to, at one moment.

    Never stored across a solve — an anchor is re-resolved every time
    :func:`constraints.solve` or :func:`constraints.satisfies` runs, which is what lets a
    moved upstream object be detected rather than silently read as stale.
    """

    point: Vec3
    """A representative world-space point for the anchor — the vertex, the face centre,
    the object's origin, or the first point of a path."""

    normal: Vec3 | None = None
    """Populated for face-like anchors (``AnchorKind.FACE``). Unit length, pointing away
    from the surface — this is what ``on`` measures vertical contact against and what
    ``coplanar_with`` aligns another object's own normal axis onto."""

    direction: Vec3 | None = None
    """Populated for edge/path/centreline-like anchors — the resolved tangent, unit
    length. This is what ``follows`` orients an instance's forward axis onto and what
    ``parallel_to``/``perpendicular_to`` measure their angle against."""

    path: tuple[Vec3, ...] | None = None
    """Populated for ``AnchorKind.PATH`` / ``AnchorKind.CENTRELINE`` — the full polyline,
    not just its endpoints, so a following constraint can walk the whole curve rather than
    interpolate a straight chord across a corner it never actually turns."""


# A face's ``feature`` string is free-form by contract (``Anchor.feature: str`` docstring)
# — there is no enum backing it. This is a *default vocabulary* for the common directional
# names an authoring surface is likely to use, not a special case per literal string: any
# object with only one face (a plane primitive) resolves to that face regardless of what
# ``feature`` says, and an unrecognised name on a multi-face object falls back to a
# deterministic choice rather than raising, since "which face" is inherently a judgement
# call this module cannot fully make on the caller's behalf.
_FACE_DIRECTIONS: dict[str, Vec3] = {
    "top": Vec3(0.0, 0.0, 1.0),
    "bottom": Vec3(0.0, 0.0, -1.0),
    "north": Vec3(0.0, 1.0, 0.0),
    "front": Vec3(0.0, 1.0, 0.0),
    "south": Vec3(0.0, -1.0, 0.0),
    "back": Vec3(0.0, -1.0, 0.0),
    "east": Vec3(1.0, 0.0, 0.0),
    "right": Vec3(1.0, 0.0, 0.0),
    "west": Vec3(-1.0, 0.0, 0.0),
    "left": Vec3(-1.0, 0.0, 0.0),
}


def _unknown_object_error(engine: EngineProtocol, object_id: str) -> ConstraintRuleError:
    known = ", ".join(sorted(engine.list_objects())) or "(none)"
    return ConstraintRuleError(
        rule="constraints.unknown_object",
        detail=f"anchor references unknown object {object_id!r}",
        suggestion=f"known objects: {known}",
    )


#: The smallest triangle that may count towards a face an :class:`~contracts.Anchor` can
#: name. A **product** floor, not a numerical one, and identical to
#: ``align.position.MIN_ANCHORABLE_FACE_CROSS_LENGTH`` — the two run the same formula for the
#: same purpose and ``align/duplicated_geometry_test.py`` fails if they diverge.
#:
#: Deliberately coarser than ``detail.edges``' and ``uv.seams``' floor, which run the same
#: formula for a *different* purpose (a dihedral angle, where every triangle a bevel produces
#: must be readable). Every triangle that survives this test becomes a group in
#: :func:`_face_groups`, and every group is a face :func:`_resolve_face` may return — via
#: ``max(..., key=score)`` for a named feature, and via ``groups[sorted(groups)[0]]`` for an
#: unrecognised one. A real 4 mm bevel on a 1 m object contributes 72 corner triangles of
#: roughly 5-10 mm to a 156-triangle mesh; admitting them would put dozens of chamfer slivers
#: into that sorted fallback, so a plain ``Anchor(kind=FACE)`` could resolve onto a 5 mm
#: chamfer and everything constrained to it would be placed against the wrong plane.
#:
#: ``EPSILON`` is reused as the value because 1e-4 m² of area is about a 14 mm triangle —
#: the right order for "too small to have been meant" — not because ``Vec3.normalized()``
#: raises below it. Those were the same number for the wrong reason, which is how this file
#: ended up carrying a second, unexplained ``1e-9`` at the call site below to compensate.
MIN_ANCHORABLE_FACE_CROSS_LENGTH = EPSILON


def _triangle_normal(vertices, triangle: tuple[int, int, int]) -> Vec3 | None:
    """The triangle's unit normal, or ``None`` when it is too small to be part of a face an
    anchor can name (:data:`MIN_ANCHORABLE_FACE_CROSS_LENGTH`).

    **This used to return ``Vec3(0, 0, 0)``** while its three sibling copies
    (``align.position``, ``detail.edges``, ``uv.seams``) returned ``None`` for the same
    input. Nothing broke, because :func:`_face_groups` re-tested the result against a
    second, undocumented ``1e-9`` — but the two lines were a single decision spelled in two
    places, so normalising the return value on its own (the obvious tidy-up) fed a
    zero-length vector into ``rotation.rotate(normal).normalized()`` and crashed anchor
    resolution. All four copies now answer ``None``, pinned by
    ``align/duplicated_geometry_test.py``.

    The **floor** still differs from the ``detail``/``uv`` copies' and must: they read a
    dihedral angle and have to see every triangle a bevel produces; this one decides what
    counts as a face. See the constant above for the measured consequence of confusing the
    two.

    Normalises by hand rather than through ``Vec3.normalized()`` so the floor above is the
    only thing rejecting anything.
    """
    a, b, c = (vertices[i] for i in triangle)
    n = (b - a).cross(c - a)
    length = n.length()
    if length < MIN_ANCHORABLE_FACE_CROSS_LENGTH:
        return None
    return Vec3(n.x / length, n.y / length, n.z / length)


def _face_groups(snapshot) -> dict[tuple[float, float, float], dict]:
    """Group the snapshot's (already-triangulated) triangles back into faces by shared
    local-space normal. A polygon triangulated by ``FakeObject.triangulated()``'s vertex
    fan always keeps every one of its triangles in the same plane, so grouping by normal
    recovers the original face without needing a second, parallel polygon representation.

    Every group's ``normal`` is unit length by construction: :func:`_triangle_normal` returns
    either a unit vector or ``None``, and ``None`` is skipped here. That invariant is
    load-bearing — :func:`_resolve_face` calls ``rotation.rotate(group["normal"]).normalized()``
    on it, which raises for a zero vector. It replaces the ``n.length() < 1e-9`` test that
    used to sit on this line, which was not a geometric threshold at all but a sentinel check
    for the zero vector the old ``_triangle_normal`` returned.
    """
    groups: dict[tuple[float, float, float], dict] = {}
    for tri in snapshot.triangles:
        n = _triangle_normal(snapshot.vertices, tri)
        if n is None:
            continue
        key = (round(n.x, 4), round(n.y, 4), round(n.z, 4))
        group = groups.setdefault(key, {"normal": n, "indices": set()})
        group["indices"].update(tri)
    return groups


def _average(vertices, indices: set[int]) -> Vec3:
    total = Vec3(0.0, 0.0, 0.0)
    for i in indices:
        total = total + vertices[i]
    return total * (1.0 / len(indices))


def _resolve_world(anchor: Anchor) -> AnchorResolution:
    return AnchorResolution(point=Vec3(0.0, 0.0, 0.0), direction=WORLD_UP)


def _resolve_object(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    snap = engine.snapshot(anchor.object_id)
    return AnchorResolution(point=snap.transform.translation)


def _resolve_bounds(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    bounds = engine.world_bounds(anchor.object_id)
    return AnchorResolution(point=bounds.centre)


def _resolve_vertex(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    snap = engine.snapshot(anchor.object_id)
    idx = anchor.index if anchor.index is not None else 0
    if idx < 0 or idx >= len(snap.vertices):
        raise ConstraintRuleError(
            rule="constraints.bad_vertex_index",
            detail=f"{anchor.object_id!r} has no vertex index {idx}",
            suggestion=f"valid range is 0..{len(snap.vertices) - 1}",
        )
    return AnchorResolution(point=snap.transform.apply(snap.vertices[idx]))


def _resolve_edge(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    snap = engine.snapshot(anchor.object_id)
    edges = snap.edges()
    idx = anchor.index if anchor.index is not None else 0
    if idx < 0 or idx >= len(edges):
        raise ConstraintRuleError(
            rule="constraints.bad_edge_index",
            detail=f"{anchor.object_id!r} has no edge index {idx}",
            suggestion=f"valid range is 0..{len(edges) - 1}",
        )
    a, b = edges[idx]
    wa = snap.transform.apply(snap.vertices[a])
    wb = snap.transform.apply(snap.vertices[b])
    diff = wb - wa
    direction = diff.normalized() if diff.length() > 1e-9 else Vec3(1.0, 0.0, 0.0)
    return AnchorResolution(point=(wa + wb) * 0.5, direction=direction)


def _resolve_face(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    snap = engine.snapshot(anchor.object_id)
    groups = _face_groups(snap)
    if not groups:
        raise ConstraintRuleError(
            rule="constraints.no_face",
            detail=f"{anchor.object_id!r} has no facial geometry to anchor to",
            suggestion="use a mesh with at least one face, or a different anchor kind",
        )
    feature = (anchor.feature or "").strip().lower()
    target_direction = _FACE_DIRECTIONS.get(feature)
    if target_direction is not None:
        def score(group: dict) -> float:
            world_normal = snap.transform.rotation.rotate(group["normal"]).normalized()
            return world_normal.dot(target_direction)

        best = max(groups.values(), key=score)
    elif len(groups) == 1:
        best = next(iter(groups.values()))
    else:
        best = groups[sorted(groups)[0]]

    local_centroid = _average(snap.vertices, best["indices"])
    world_point = snap.transform.apply(local_centroid)
    world_normal = snap.transform.rotation.rotate(best["normal"]).normalized()
    return AnchorResolution(point=world_point, normal=world_normal)


def _resolve_path(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    snap = engine.snapshot(anchor.object_id)
    world_points = tuple(snap.transform.apply(v) for v in snap.vertices)
    diff = world_points[-1] - world_points[0]
    direction = diff.normalized() if diff.length() > 1e-9 else Vec3(1.0, 0.0, 0.0)
    return AnchorResolution(point=world_points[0], direction=direction, path=world_points)


_RESOLVERS = {
    AnchorKind.OBJECT: _resolve_object,
    AnchorKind.BOUNDS: _resolve_bounds,
    AnchorKind.VERTEX: _resolve_vertex,
    AnchorKind.EDGE: _resolve_edge,
    AnchorKind.FACE: _resolve_face,
    AnchorKind.PATH: _resolve_path,
    AnchorKind.CENTRELINE: _resolve_path,
}


def resolve_anchor(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    """Resolve one symbolic anchor against the engine's *current* geometry.

    ``AnchorKind.WORLD`` (see ``Anchor.world_up()``) resolves with no object lookup at
    all — ``direction`` is world up, ``point`` is the origin. Every other kind resolves
    through ``anchor.object_id``.

    Raises :class:`~constraints.ConstraintRuleError` — never a bare ``KeyError`` or
    ``AttributeError`` — when ``anchor.object_id`` does not name a live object. Gate A 4.2
    requires an agent be told which id was missing and what to try next, not handed a
    traceback it cannot act on; ``engine.exists()``/``engine.list_objects()`` are what
    make that suggestion possible without a bare lookup failure.
    """
    if anchor.kind == AnchorKind.WORLD:
        return _resolve_world(anchor)

    if not anchor.object_id:
        raise ConstraintRuleError(
            rule="constraints.missing_object_id",
            detail=f"a {anchor.kind.value!r} anchor needs an object_id and none was given",
            suggestion="set Anchor.object_id to the target object's id",
        )

    if not engine.exists(anchor.object_id):
        raise _unknown_object_error(engine, anchor.object_id)

    resolver = _RESOLVERS.get(anchor.kind)
    if resolver is None:
        raise ConstraintRuleError(
            rule="constraints.unsupported_anchor_kind",
            detail=f"{anchor.kind!r} is not a supported anchor kind",
            suggestion="",
        )
    return resolver(engine, anchor)
