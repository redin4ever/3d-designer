"""Anchor resolution — turning a symbolic reference into world geometry.

An ``Anchor`` (``src/contracts/constraints.py``) names a target *symbolically*:
``stair_01.outer_edge``, never a resolved coordinate. That is the entire mechanism behind
live re-solve (ADR-002) — the stair moves, the anchor's identity survives, and the next
resolve call reads the new geometry. Anything that resolves an anchor once and caches the
number defeats the reason anchors are symbolic in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import Anchor, AnchorKind, ConstraintError, EngineProtocol, Vec3, WORLD_UP

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


def _unknown_object_error(engine: EngineProtocol, object_id: str) -> ConstraintError:
    known = ", ".join(sorted(engine.list_objects())) or "(none)"
    return ConstraintError(
        rule="constraints.unknown_object",
        detail=f"anchor references unknown object {object_id!r}",
        suggestion=f"known objects: {known}",
    )


def _triangle_normal(vertices, triangle: tuple[int, int, int]) -> Vec3:
    a, b, c = (vertices[i] for i in triangle)
    n = (b - a).cross(c - a)
    if n.length() < 1e-12:
        return Vec3(0.0, 0.0, 0.0)
    return n.normalized()


def _face_groups(snapshot) -> dict[tuple[float, float, float], dict]:
    """Group the snapshot's (already-triangulated) triangles back into faces by shared
    local-space normal. A polygon triangulated by ``FakeObject.triangulated()``'s vertex
    fan always keeps every one of its triangles in the same plane, so grouping by normal
    recovers the original face without needing a second, parallel polygon representation."""
    groups: dict[tuple[float, float, float], dict] = {}
    for tri in snapshot.triangles:
        n = _triangle_normal(snapshot.vertices, tri)
        if n.length() < 1e-9:
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
        raise ConstraintError(
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
        raise ConstraintError(
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
        raise ConstraintError(
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

    Raises :class:`~contracts.ConstraintError` — never a bare ``KeyError`` or
    ``AttributeError`` — when ``anchor.object_id`` does not name a live object. Gate A 4.2
    requires an agent be told which id was missing and what to try next, not handed a
    traceback it cannot act on; ``engine.exists()``/``engine.list_objects()`` are what
    make that suggestion possible without a bare lookup failure.
    """
    if anchor.kind == AnchorKind.WORLD:
        return _resolve_world(anchor)

    if not anchor.object_id:
        raise ConstraintError(
            rule="constraints.missing_object_id",
            detail=f"a {anchor.kind.value!r} anchor needs an object_id and none was given",
            suggestion="set Anchor.object_id to the target object's id",
        )

    if not engine.exists(anchor.object_id):
        raise _unknown_object_error(engine, anchor.object_id)

    resolver = _RESOLVERS.get(anchor.kind)
    if resolver is None:
        raise ConstraintError(
            rule="constraints.unsupported_anchor_kind",
            detail=f"{anchor.kind!r} is not a supported anchor kind",
            suggestion="",
        )
    return resolver(engine, anchor)
