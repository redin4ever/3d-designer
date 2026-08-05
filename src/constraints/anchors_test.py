"""Tests for ``resolve_anchor`` — turning a symbolic reference into world geometry.

Anchors are symbolic on purpose (``contracts.Anchor`` docstring): ``stair_01.outer_edge``
survives the stair moving, a resolved coordinate does not. Every test here checks that
resolution reads *current* engine geometry rather than something baked in at construction
time, and that a missing object fails through the typed error contract, never a bare
``KeyError``.
"""

from __future__ import annotations

import pytest

from contracts import (
    Anchor,
    AnchorKind,
    ConstraintError,
    EPSILON,
    Quat,
    Transform,
    Vec3,
    WORLD_UP,
)
from constraints import resolve_anchor
from testing import unit_cube


def test_world_up_anchor_resolves_without_any_object_lookup(engine) -> None:
    """``Anchor.world_up()`` is the target ``plumb`` constraints resolve against
    (``ConstraintKind.PLUMB`` docstring) — it must resolve on a scene with zero objects,
    since a scene's very first object can still be constrained plumb."""
    resolution = resolve_anchor(engine, Anchor.world_up())

    assert resolution.direction is not None
    assert resolution.direction.as_tuple() == pytest.approx(WORLD_UP.as_tuple())


def test_object_anchor_resolves_to_its_world_space_origin(engine) -> None:
    """``offset_from``, ``centred_on`` and friends all target a plain object anchor and
    need a single reference point for it — get this wrong and every constraint built on
    top of an object anchor inherits the same wrong point."""
    engine.create_primitive("beam", "cube", Vec3(0.2, 0.2, 3.0), Transform(translation=Vec3(3, 4, 5)))

    resolution = resolve_anchor(engine, Anchor(kind=AnchorKind.OBJECT, object_id="beam"))

    assert resolution.point.as_tuple() == pytest.approx((3.0, 4.0, 5.0), abs=EPSILON)


def test_bounds_anchor_resolves_to_the_aabb_centre_not_the_objects_origin(engine) -> None:
    """A ``bounds`` anchor is meant to answer "the middle of this object's extent", which
    is a different point from its transform origin the moment the mesh is not modelled
    symmetrically about that origin — collapsing the two silently mis-centres anything
    built on this anchor."""
    verts, faces = unit_cube(Vec3(2, 1, 1))
    shifted = [v + Vec3(1, 0.5, 0.5) for v in verts]  # local box now spans [0,2]x[0,1]x[0,1]
    engine.create_mesh("cabinet", shifted, faces, Transform(translation=Vec3(10, 0, 0)))

    resolution = resolve_anchor(engine, Anchor(kind=AnchorKind.BOUNDS, object_id="cabinet"))

    assert resolution.point.as_tuple() == pytest.approx((11.0, 0.5, 0.5), abs=EPSILON)


def test_vertex_anchor_resolves_to_the_transformed_world_position(engine) -> None:
    """``ends_at`` and ``spacing`` corner cases both need an exact vertex, not an
    approximate face centre — the transform (translation *and* rotation) must be applied,
    not just translation."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)]
    faces = [(0, 1, 2), (0, 1, 3), (0, 2, 3)]
    xform = Transform(translation=Vec3(5, 0, 0), rotation=Quat.from_axis_angle(Vec3(0, 0, 1), 1.5707963))
    engine.create_mesh("gizmo", verts, faces, xform)

    resolution = resolve_anchor(engine, Anchor(kind=AnchorKind.VERTEX, object_id="gizmo", index=1))

    expected = xform.apply(verts[1])
    assert resolution.point.as_tuple() == pytest.approx(expected.as_tuple(), abs=1e-4)


def test_face_anchor_top_of_a_box_has_an_upward_normal_and_sits_at_the_ceiling(engine) -> None:
    """``on`` measures vertical contact against exactly this: a face anchor's point must
    sit at the surface itself, and its normal must point away from the solid, or ``on``
    cannot tell "resting on top" from "resting underneath"."""
    engine.create_primitive("crate", "cube", Vec3(1.0, 2.0, 0.6), Transform(translation=Vec3(3, -1, 4)))
    bounds = engine.world_bounds("crate")

    resolution = resolve_anchor(engine, Anchor(kind=AnchorKind.FACE, object_id="crate", feature="top"))

    assert resolution.point.z == pytest.approx(bounds.maximum.z, abs=EPSILON)
    assert bounds.minimum.x - EPSILON <= resolution.point.x <= bounds.maximum.x + EPSILON
    assert bounds.minimum.y - EPSILON <= resolution.point.y <= bounds.maximum.y + EPSILON
    assert resolution.normal is not None
    assert resolution.normal.as_tuple() == pytest.approx((0.0, 0.0, 1.0), abs=1e-6)


def test_edge_anchor_direction_lies_along_the_indexed_edge(engine) -> None:
    """``Anchor.index`` selects into ``MeshSnapshot.edges()``'s canonical ordering
    (``geometry.py``'s own contract for ``bevel_edges``) — the same ordering has to be
    honoured here, or an edge index that means one edge to the caller resolves to a
    different edge inside the solver."""
    verts = [Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(0, 3, 0)]
    engine.create_mesh("tri", verts, [(0, 1, 2)])
    a, b = engine.snapshot("tri").edges()[0]

    resolution = resolve_anchor(engine, Anchor(kind=AnchorKind.EDGE, object_id="tri", index=0))

    expected_dir = (verts[b] - verts[a]).normalized()
    assert resolution.direction is not None
    dot = resolution.direction.normalized().dot(expected_dir)
    assert abs(dot) == pytest.approx(1.0, abs=1e-6), "edge direction is not parallel to the indexed edge"


def test_unknown_anchor_object_raises_constrainterror_not_a_bare_keyerror(engine) -> None:
    """A model that gets an object id wrong needs to be told which id and what exists
    instead (Gate A 4.2) — a bare ``KeyError`` surfaces a traceback it cannot act on and
    it loops on the same broken call."""
    engine.create_primitive("post_1", "cube", Vec3(0.1, 0.1, 1.0))

    with pytest.raises(ConstraintError, match="post_9"):
        resolve_anchor(engine, Anchor(kind=AnchorKind.OBJECT, object_id="post_9"))
