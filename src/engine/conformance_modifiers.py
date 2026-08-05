"""Conformance checks for ``ModifierOps`` — bevel, boolean, array-along-curve, repairs.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/modifiers.py``.
``check_array_along_curve_keeps_instances_plumb_on_a_slope`` is the single most important
behavioural test in the product — see its docstring. Part of the shared suite: see
``conformance.py`` for how ``conformance_test.py`` and ``blender_test.py`` assemble it.
"""

from __future__ import annotations

import pytest

from contracts import EngineError, EngineProtocol, Transform, Vec3, WORLD_UP
from testing import unit_cube

__all__ = [
    "check_bevel_refuses_unapplied_scale",
    "check_bevel_edges_with_explicit_selection_increases_triangle_count",
    "check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged",
    "check_boolean_union_matches_bounds_and_removes_cutter",
    "check_array_along_curve_keeps_instances_plumb_on_a_slope",
    "check_array_along_curve_tilts_when_upright_is_disabled",
    "check_array_includes_forced_corner_positions",
    "check_array_uses_the_caller_supplied_name_template",
    "check_merge_by_distance_welds_coincident_vertices",
    "check_fill_holes_closes_an_open_box",
    "check_fill_holes_reports_what_it_could_not_do",
    "check_separate_loose_splits_disconnected_shells",
    "check_bevel_edges_moves_only_the_selected_edges_geometry",
]


def check_bevel_refuses_unapplied_scale(engine: EngineProtocol) -> None:
    """Bevel width is computed in object space; unapplied non-uniform scale produces
    uneven bevels that look fine until measured. The engine must refuse rather than
    silently producing wrong geometry."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.set_transform("box", Transform(scale=Vec3(3, 1, 1)))

    with pytest.raises(EngineError) as exc:
        engine.bevel_edges("box", width=0.01)

    assert exc.value.rule == "engine.unapplied_scale"
    assert exc.value.suggestion, "an error with no suggested next step makes agents loop"


def check_bevel_edges_with_explicit_selection_increases_triangle_count(
    engine: EngineProtocol,
) -> None:
    """If an explicit edge selection does not change the mesh, ``bevel_edges`` is either a
    no-op or is beveling the wrong (or every) edge — both invisible until a detail pass's
    "which edges got beveled" heuristic quietly stops mattering."""
    oid = engine.create_primitive("blk", "cube", Vec3(1, 1, 1))
    before = engine.snapshot(oid).triangle_count
    edges = engine.snapshot(oid).edges()

    engine.bevel_edges(oid, width=0.05, segments=2, edge_indices=edges[:4])

    assert engine.snapshot(oid).triangle_count > before


def check_bevel_edges_with_empty_selection_leaves_triangle_count_unchanged(
    engine: EngineProtocol,
) -> None:
    """The counterpart to the check above: an empty selection proves nothing if
    ``bevel_edges`` bevels blanket-everything regardless of what ``edge_indices`` says."""
    oid = engine.create_primitive("blk", "cube", Vec3(1, 1, 1))
    before = engine.snapshot(oid).triangle_count

    engine.bevel_edges(oid, width=0.05, segments=2, edge_indices=[])

    assert engine.snapshot(oid).triangle_count == before


def check_boolean_union_matches_bounds_and_removes_cutter(engine: EngineProtocol) -> None:
    """A union whose bounds fall short of the two inputs' combined extent has silently
    dropped geometry — the classic boolean failure. The cutter surviving as an orphaned
    duplicate is the other: it would render twice and double-count in a polygon budget."""
    a = engine.create_primitive("cube_a", "cube", Vec3(2, 2, 2))
    b = engine.create_primitive(
        "cube_b", "cube", Vec3(2, 2, 2), Transform(translation=Vec3(1, 0, 0))
    )
    bounds_a, bounds_b = engine.world_bounds(a), engine.world_bounds(b)

    engine.boolean(a, b, mode="union", solver="exact")

    result = engine.world_bounds(a)
    for axis in ("x", "y", "z"):
        expected_min = min(getattr(bounds_a.minimum, axis), getattr(bounds_b.minimum, axis))
        expected_max = max(getattr(bounds_a.maximum, axis), getattr(bounds_b.maximum, axis))
        assert getattr(result.minimum, axis) == pytest.approx(expected_min)
        assert getattr(result.maximum, axis) == pytest.approx(expected_max)
    assert not engine.exists(b), "the cutter must not linger as an orphaned duplicate"


def check_array_along_curve_keeps_instances_plumb_on_a_slope(engine: EngineProtocol) -> None:
    """The single most important behavioural test in the product. Posts normal to a stair
    rake instead of plumb — leaning at the stair angle — is the classic naive-generator
    failure this tool exists to prevent."""
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    rake = [Vec3(0, 0, 0), Vec3(3.0, 0, 1.8)]

    ids = engine.array_along_curve("post", rake, spacing=1.0, keep_upright=True)

    assert len(ids) >= 3
    for oid in ids:
        up = engine.snapshot(oid).transform.rotation.rotate(WORLD_UP)
        assert up.z == pytest.approx(1.0, abs=1e-6), f"{oid} is not plumb"


def check_array_along_curve_tilts_when_upright_is_disabled(engine: EngineProtocol) -> None:
    """The wrong behaviour must be reachable, or the plumb check above proves nothing —
    it would pass even if ``keep_upright`` were silently ignored."""
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    rake = [Vec3(0, 0, 0), Vec3(3.0, 0, 1.8)]

    ids = engine.array_along_curve("post", rake, spacing=1.0, keep_upright=False)

    ups = [engine.snapshot(o).transform.rotation.rotate(WORLD_UP) for o in ids]
    assert any(u.z < 0.95 for u in ups), "no instance tilted — the two modes are identical"


def check_array_includes_forced_corner_positions(engine: EngineProtocol) -> None:
    """A fixed pitch with no corner-aware resampling produces either a gap or a doubled
    instance at a direction change — visible as a baluster embedded in, or floating off,
    a railing corner."""
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    path = [Vec3(0, 0, 0), Vec3(3.0, 0, 0), Vec3(3.0, 2.0, 0)]
    corner = Vec3(3.0, 0, 0)

    ids = engine.array_along_curve(
        "post", path, spacing=1.7, keep_upright=True, extra_points=[corner]
    )

    positions = [engine.snapshot(o).transform.translation for o in ids]
    assert any((p - corner).length() < 1e-6 for p in positions), "no post landed on the corner"


def check_array_uses_the_caller_supplied_name_template(engine: EngineProtocol) -> None:
    """Instance ids must be predictable *before* the call, so an operation can pre-declare a
    ``ConstraintSet`` per instance and have live re-solve reach individual balusters rather
    than only the array as a whole."""
    engine.create_primitive("baluster", "cube", Vec3(0.04, 0.04, 0.8))

    ids = engine.array_along_curve(
        "baluster",
        [Vec3(0, 0, 0), Vec3(2, 0, 0)],
        spacing=0.5,
        keep_upright=True,
        name_template="rail_bal_{index:02d}",
    )

    assert ids[0] == "rail_bal_00"
    assert all(i.startswith("rail_bal_") for i in ids)


def check_merge_by_distance_welds_coincident_vertices(engine: EngineProtocol) -> None:
    """Unwelded coincident vertices are invisible in a render but break every downstream
    operation that assumes a shared edge — bevel, solidify, and boolean all see a crack."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(1, 1, 0)]
    oid = engine.create_mesh("m", verts, [(0, 1, 2)])

    outcome = engine.merge_by_distance(oid, 1e-6)

    assert outcome.fixed == 1
    assert outcome.complete
    assert engine.snapshot(oid).vertex_count == 3


def check_fill_holes_closes_an_open_box(engine: EngineProtocol) -> None:
    """An unfilled hole exported as-is is a hole in the final asset — light leaks through a
    wall, or a game engine's collision mesh has a gap a player falls through."""
    verts, faces = unit_cube()
    oid = engine.create_mesh("open", verts, faces[:-1])

    outcome = engine.fill_holes(oid)

    assert outcome.fixed >= 1
    assert engine.fill_holes(oid).fixed == 0, "a second pass found holes the first missed"


def check_fill_holes_reports_what_it_could_not_do(engine: EngineProtocol) -> None:
    """A bare count cannot distinguish "nothing to do" from "found work and refused it" —
    both are zero. Without ``skipped`` and ``reason``, a caller reports a clean mesh that
    still has a hole in it."""
    verts, faces = unit_cube()
    oid = engine.create_mesh("open", verts, faces[:-1])

    outcome = engine.fill_holes(oid, max_sides=3)

    assert outcome.fixed == 0
    assert outcome.skipped >= 1, "the 4-sided hole was skipped but not reported"
    assert not outcome.complete
    assert "max_sides" in outcome.reason


def check_separate_loose_splits_disconnected_shells(engine: EngineProtocol) -> None:
    """If disconnected shells stay merged as one object, per-object operations (transform,
    material assignment, export as a separate part) apply to both pieces at once."""
    verts = [
        Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0),
        Vec3(5, 5, 5), Vec3(6, 5, 5), Vec3(5, 6, 5),
    ]
    oid = engine.create_mesh("two", verts, [(0, 1, 2), (3, 4, 5)])

    parts = engine.separate_loose(oid)

    assert len(parts) == 2
    assert not engine.exists(oid)


def _disjoint_edge_pair(edges: list[tuple[int, int]]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Two edges sharing no vertex, so bevelling one cannot legitimately move a vertex the
    other touches. Searched rather than hardcoded to ``edges[0]``/``edges[4]`` because
    ``MeshSnapshot.edges()``'s exact ordering (which diagonal a quad's triangulation picks)
    is an engine-specific implementation detail this check must not assume."""
    first = edges[0]
    for other in edges[1:]:
        if not set(first) & set(other):
            return first, other
    raise AssertionError("could not find two vertex-disjoint edges on this mesh")


def _has_close(positions, target, tol: float = 1e-6) -> bool:
    return any((p - target).length() < tol for p in positions)


def check_bevel_edges_moves_only_the_selected_edges_geometry(engine: EngineProtocol) -> None:
    """Blender-only, added in response to a conformance audit. The two triangle-count
    checks above both pass for an implementation that ignores WHICH edges were selected and
    always bevels a fixed number of edges regardless of ``edge_indices`` — enabling exactly
    the blanket-bevel behaviour the ``ModifierOps.bevel_edges`` docstring calls an
    artificiality tell. This bevels two different single-edge selections on two fresh,
    identical cubes and checks that a vertex touching only the UNselected edge stays
    exactly put in each, while a vertex touching the selected edge moves. Blender-only
    because ``FakeEngine.bevel_edges`` never touches ``vertices`` at all — it only extends
    the face list with duplicates of the first face to approximate triangle-count growth
    (see its own source) — so no vertex ever moves on the fake side regardless of
    selection; this check's premise cannot hold against it."""
    verts, faces = unit_cube()
    oid_a = engine.create_mesh("bevel_sel_a", verts, faces)
    oid_b = engine.create_mesh("bevel_sel_b", verts, faces)

    edges = engine.snapshot(oid_a).edges()
    edge_a, edge_b = _disjoint_edge_pair(edges)

    pre = engine.snapshot(oid_a).world_vertices()
    point_a0, point_a1 = pre[edge_a[0]], pre[edge_a[1]]
    point_b0, point_b1 = pre[edge_b[0]], pre[edge_b[1]]

    engine.bevel_edges(oid_a, width=0.05, segments=2, edge_indices=[edge_a])
    engine.bevel_edges(oid_b, width=0.05, segments=2, edge_indices=[edge_b])

    post_a = engine.snapshot(oid_a).world_vertices()
    post_b = engine.snapshot(oid_b).world_vertices()

    assert not (_has_close(post_a, point_a0) and _has_close(post_a, point_a1)), (
        "bevelling edge_a left both its endpoints exactly where they started"
    )
    assert _has_close(post_a, point_b0) and _has_close(post_a, point_b1), (
        "bevelling edge_a moved a vertex that only touches the UNselected edge_b — "
        "selection is being ignored"
    )
    assert not (_has_close(post_b, point_b0) and _has_close(post_b, point_b1)), (
        "bevelling edge_b left both its endpoints exactly where they started"
    )
    assert _has_close(post_b, point_a0) and _has_close(post_b, point_a1), (
        "bevelling edge_b moved a vertex that only touches the UNselected edge_a — "
        "selection is being ignored"
    )
