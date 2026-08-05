"""Conformance checks for ``MeshOps`` — creation, transforms, lookup, world bounds.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/mesh.py``. Part of
the shared suite: ``conformance_test.py`` runs these against ``FakeEngine``,
``blender_test.py`` runs the same functions against the real ``BlenderEngine``. See
``conformance.py`` for how the two suites are assembled and why a handful of checks are
Blender-only.
"""

from __future__ import annotations

import pytest

from contracts import EngineError, EngineProtocol, Transform, Vec3
from testing import unit_cube

__all__ = [
    "check_primitive_has_expected_world_bounds",
    "check_create_mesh_produces_a_closed_manifold",
    "check_create_primitive_returns_the_actual_assigned_id",
    "check_apply_transform_bakes_scale_into_vertices",
    "check_unknown_object_error_names_what_exists",
]


def check_primitive_has_expected_world_bounds(engine: EngineProtocol) -> None:
    """If this fails, every generated primitive is the wrong physical size — a "2m railing"
    request silently produces something else, undetectable in a screenshot."""
    engine.create_primitive("box", "cube", Vec3(2.0, 4.0, 1.0))
    bounds = engine.world_bounds("box")
    assert bounds.size.x == pytest.approx(2.0)
    assert bounds.size.y == pytest.approx(4.0)
    assert bounds.size.z == pytest.approx(1.0)


def check_create_mesh_produces_a_closed_manifold(engine: EngineProtocol) -> None:
    """A box with a boundary edge is not watertight. Every manifold check downstream
    (boolean pre-checks, solidify, export) is meaningless if ``create_mesh`` itself leaks."""
    verts, faces = unit_cube()
    oid = engine.create_mesh("box", verts, faces)
    snap = engine.snapshot(oid)
    counts: dict[tuple[int, int], int] = {}
    for tri in snap.triangles:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            key = (min(a, b), max(a, b))
            counts[key] = counts.get(key, 0) + 1
    boundary = [e for e, n in counts.items() if n == 1]
    assert boundary == [], f"left {len(boundary)} boundary edges in a mesh meant to be closed"


def check_create_primitive_returns_the_actual_assigned_id(engine: EngineProtocol) -> None:
    """A caller that keeps using its *requested* id after a collision is silently writing to
    someone else's object, or to nothing — bpy renames on collision rather than erroring."""
    first = engine.create_primitive("dup", "cube", Vec3(1, 1, 1))
    second = engine.create_primitive("dup", "cube", Vec3(1, 1, 1))
    assert second != first, "a name collision must be resolved by renaming, not overwriting"
    assert engine.exists(first) and engine.exists(second)
    assert second in engine.list_objects()


def check_apply_transform_bakes_scale_into_vertices(engine: EngineProtocol) -> None:
    """Unapplied scale is invisible in a viewport and corrupts bevel width, boolean results
    and physics. Asserting only the transform field would pass even if bpy's apply operator
    silently no-opped; world bounds prove the vertices actually moved."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.set_transform("box", Transform(scale=Vec3(2, 2, 2)))
    assert engine.snapshot("box").transform.has_unapplied_scale()

    engine.apply_transform("box", location=False, rotation=False, scale=True)

    snap = engine.snapshot("box")
    assert not snap.transform.has_unapplied_scale()
    assert snap.world_bounds().size.x == pytest.approx(2.0)


def check_unknown_object_error_names_what_exists(engine: EngineProtocol) -> None:
    """An error that does not say what *does* exist sends an agent guessing at typos with no
    way to self-correct — Gate A 4.2's "tell it which rule broke and what to try next"."""
    engine.create_primitive("floor", "plane", Vec3(4, 4, 0))

    with pytest.raises(EngineError) as exc:
        engine.snapshot("flooor")

    assert exc.value.rule == "engine.unknown_object"
    assert "floor" in exc.value.suggestion, "the error should say what does exist"
