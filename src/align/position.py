"""``make_coplanar``, ``make_flush`` — the position-affecting immediate-snap alignments.

Both reuse ``constraints.solve``/``transform_for`` directly rather than re-deriving
plane-projection or face-support arithmetic: ``make_flush`` is exactly
``ConstraintKind.FLUSH_WITH`` resolved once, and ``make_coplanar`` (when ``face`` is not
given) is exactly ``ConstraintKind.COPLANAR_WITH``. ``constraints.solve`` already carries
the "a constraint only ever moves what it names" invariant this module also promises —
reusing it is what keeps the two promises from drifting apart (see ``align/README.md``).

``make_coplanar``'s ``face: int`` path is the one piece of new geometry in this file:
``contracts.Anchor`` has no numbered-face selector for ``AnchorKind.FACE`` (only
``AnchorKind.VERTEX``/``EDGE`` read ``Anchor.index`` — see
``constraints/CLAUDE.md``'s "Anchor.index selects into MeshSnapshot.edges()" note), so
picking "the object's 3rd planar face" needs its own small resolver here.
"""

from __future__ import annotations

from contracts import (
    EPSILON,
    Anchor,
    AnchorKind,
    Constraint,
    ConstraintKind,
    ConstraintSet,
    EngineProtocol,
    ToolError,
    Transform,
    Vec3,
)
from constraints import resolve_anchor, solve, transform_for

from ._geom import rotation_aligning, transforms_close
from ._util import normal_angle_deg, require_axis, require_object
from .orientation import measure_angle
from .results import AlignResult

__all__ = ["make_coplanar", "make_flush"]


def _triangle_normal(vertices, triangle: tuple[int, int, int]) -> Vec3 | None:
    a, b, c = (vertices[i] for i in triangle)
    n = (b - a).cross(c - a)
    # EPSILON, not 1e-12, and None rather than an unnormalized near-zero vector: a
    # sliver between the two thresholds trips normalized(), and returning the raw
    # cross product silently hands callers a non-unit 'normal' they treat as unit.
    return None if n.length() < EPSILON else n.normalized()


def _nth_face(engine: EngineProtocol, object_id: str, face: int) -> tuple[Vec3, Vec3]:
    """The ``(world_point, world_normal)`` of ``object_id``'s ``face``-th planar face
    group, in a deterministic order.

    Groups the snapshot's triangles by local-space normal — the same technique
    ``constraints.anchors``' private ``_face_groups`` uses (not exported; see the module
    docstring) — then indexes into the groups sorted by their rounded normal key, which is
    stable across calls because it does not depend on triangle iteration order.
    """
    snap = engine.snapshot(object_id)
    groups: dict[tuple[float, float, float], dict] = {}
    for tri in snap.triangles:
        n = _triangle_normal(snap.vertices, tri)
        if n is None:
            continue  # degenerate sliver — no orientation to group by
        key = (round(n.x, 4), round(n.y, 4), round(n.z, 4))
        group = groups.setdefault(key, {"normal": n, "indices": set()})
        group["indices"].update(tri)
    if not groups:
        raise ToolError(
            "align.no_face",
            f"{object_id!r} has no facial geometry to align to",
            "use a mesh with at least one face",
        )
    keys = sorted(groups)
    if face < 0 or face >= len(keys):
        raise ToolError(
            "align.bad_face_index",
            f"{object_id!r} has no face index {face}",
            f"valid range is 0..{len(keys) - 1}",
        )
    group = groups[keys[face]]
    indices = group["indices"]
    total = Vec3(0.0, 0.0, 0.0)
    for i in indices:
        total = total + snap.vertices[i]
    local_centroid = total * (1.0 / len(indices))
    world_point = snap.transform.apply(local_centroid)
    world_normal = snap.transform.rotation.rotate(group["normal"]).normalized()
    return world_point, world_normal


def make_coplanar(
    engine: EngineProtocol, object_id: str, to: str, *, face: int | None = None
) -> AlignResult:
    """Rotate and move ``object_id`` so every one of its own points lands in ``to``'s
    face plane (``face=None`` picks ``to``'s default face the way
    ``AnchorKind.FACE``/``feature=""`` already does; ``face=i`` picks the ``i``-th planar
    face group explicitly).

    Verified by plane-distance, not by trusting the rotation: every vertex of
    ``object_id``, transformed by the resulting placement, must have zero signed distance
    to the target plane — not just the object's own origin.

    Builds the candidate transform directly from ``(point, normal)`` — minimal rotation of
    local +Z onto ``normal`` (``_geom.rotation_aligning``, the same formula
    ``constraints.transform_for`` composes from), then the position's component along
    ``normal`` replaced to match the plane — rather than routing through
    ``constraints.solve`` the way ``make_plumb``/``make_flush`` do, because ``face=int``
    has no ``Anchor`` representation to solve against (see the module docstring) and using
    one construction for both branches keeps them from silently disagreeing.
    """
    require_object(engine, object_id, role="object_id")
    require_object(engine, to, role="to")

    if face is None:
        resolution = resolve_anchor(engine, Anchor(kind=AnchorKind.FACE, object_id=to, feature=""))
        point = resolution.point
        normal = resolution.normal if resolution.normal is not None else Vec3(0.0, 0.0, 1.0)
    else:
        point, normal = _nth_face(engine, to, face)
    normal = normal.normalized()

    before = normal_angle_deg(engine, object_id, normal)
    snap = engine.snapshot(object_id)
    current_normal_axis = snap.transform.rotation.rotate(Vec3(0.0, 0.0, 1.0)).normalized()
    delta = rotation_aligning(current_normal_axis, normal)
    new_rotation = (delta * snap.transform.rotation).normalized()
    current_pos = snap.transform.translation
    scalar = normal.dot(point)
    new_pos = current_pos + normal * (scalar - current_pos.dot(normal))
    candidate = Transform(translation=new_pos, rotation=new_rotation, scale=snap.transform.scale)

    if transforms_close(candidate, snap.transform):
        return AlignResult(
            object_id=object_id, changed=False, angle_before_deg=before, angle_after_deg=before,
            detail=f"{object_id} is already coplanar with {to} within tolerance",
        )
    engine.set_transform(object_id, candidate)
    after = normal_angle_deg(engine, object_id, normal)
    return AlignResult(
        object_id=object_id, changed=True, angle_before_deg=before, angle_after_deg=after,
        detail=f"moved {object_id} into {to}'s plane",
    )


def make_flush(engine: EngineProtocol, object_id: str, to: str, *, axis: str) -> AlignResult:
    """Move ``object_id`` along ``axis`` only, so its face on that axis shares a plane
    with ``to``'s — no gap, no overlap — leaving the other two position axes and all
    rotation untouched.

    ``axis`` is a required local axis name (``"x"``, ``"y"`` or ``"z"``, world-aligned
    since ``ConstraintKind.FLUSH_WITH`` reads ``Constraint.axis`` as a world direction, not
    a bitmask — see ``constraints/CLAUDE.md``).

    Reuses ``constraints.solve`` for the position arithmetic (``FLUSH_WITH`` mirrors the
    target's own half-extent, never the mover's — see ``constraints/_position.py``'s own
    comment on why) but keeps ``object_id``'s *current* rotation and scale verbatim rather
    than trusting ``constraints.transform_for``'s up/forward reconstruction to reproduce
    them bit-for-bit: ``flush_with`` never touches orientation, so there is nothing to
    reconstruct.
    """
    require_object(engine, object_id, role="object_id")
    require_object(engine, to, role="to")
    axis_vec = require_axis(axis)
    before = measure_angle(engine, object_id, to)

    cs = ConstraintSet(
        object_id=object_id,
        constraints=(
            Constraint(
                kind=ConstraintKind.FLUSH_WITH,
                target=Anchor(kind=AnchorKind.OBJECT, object_id=to),
                axis=axis_vec,
            ),
        ),
    )
    placement = solve(engine, cs)
    current = engine.snapshot(object_id).transform
    candidate = Transform(translation=placement.position, rotation=current.rotation, scale=current.scale)

    if transforms_close(candidate, current):
        return AlignResult(
            object_id=object_id, changed=False, angle_before_deg=before, angle_after_deg=before,
            detail=f"{object_id} is already flush with {to} on {axis}",
        )
    engine.set_transform(object_id, candidate)
    after = measure_angle(engine, object_id, to)
    return AlignResult(
        object_id=object_id, changed=True, angle_before_deg=before, angle_after_deg=after,
        detail=f"moved {object_id} flush with {to} on {axis}",
    )
