"""Tests for the shared test engine.

The fake is depended on by every other module's suite, so a bug here produces false
confidence everywhere at once. It is main-agent-owned infrastructure and gets its own
tests for the same reason a shared library does.
"""

from __future__ import annotations

import math

import pytest

from contracts import EngineError, EngineUnavailable, Quat, Transform, Vec3, WORLD_UP
from testing import FakeEngine, rotation_from_up_to, sample_polyline, unit_cube


def test_primitive_has_expected_world_bounds(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(2.0, 4.0, 1.0))
    bounds = engine.world_bounds("box")
    assert bounds.size.x == pytest.approx(2.0)
    assert bounds.size.y == pytest.approx(4.0)
    assert bounds.size.z == pytest.approx(1.0)


def test_unit_cube_is_closed(engine: FakeEngine) -> None:
    """Every edge of a closed box bounds exactly two faces. If the fake produced an open
    box, every manifold test written against it would be meaningless."""
    verts, faces = unit_cube()
    engine.create_mesh("box", verts, faces)
    snap = engine.snapshot("box")
    counts: dict[tuple[int, int], int] = {}
    for tri in snap.triangles:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            key = (min(a, b), max(a, b))
            counts[key] = counts.get(key, 0) + 1
    boundary = [e for e, n in counts.items() if n == 1]
    assert boundary == [], f"unit cube left {len(boundary)} boundary edges"


def test_apply_transform_bakes_scale_into_vertices(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.set_transform("box", Transform(scale=Vec3(2, 2, 2)))
    assert engine.snapshot("box").transform.has_unapplied_scale()

    engine.apply_transform("box", location=False, rotation=False, scale=True)

    snap = engine.snapshot("box")
    assert not snap.transform.has_unapplied_scale()
    assert snap.world_bounds().size.x == pytest.approx(2.0)


def test_bevel_refuses_unapplied_scale(engine: FakeEngine) -> None:
    """Unapplied non-uniform scale silently produces uneven bevels and is invisible in a
    viewport. The engine refuses rather than producing quietly wrong geometry."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.set_transform("box", Transform(scale=Vec3(3, 1, 1)))

    with pytest.raises(EngineError) as exc:
        engine.bevel_edges("box", width=0.01)

    assert exc.value.rule == "engine.unapplied_scale"
    assert exc.value.suggestion, "an error with no suggested next step makes agents loop"


def test_array_along_curve_keeps_instances_plumb_on_a_slope(engine: FakeEngine) -> None:
    """The single most common naive-generator error: posts normal to a stair rake lean at
    the stair angle instead of standing vertical."""
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    rake = [Vec3(0, 0, 0), Vec3(3.0, 0, 1.8)]

    ids = engine.array_along_curve("post", rake, spacing=1.0, keep_upright=True)

    assert len(ids) >= 3
    for oid in ids:
        up = engine.snapshot(oid).transform.rotation.rotate(WORLD_UP)
        assert up.z == pytest.approx(1.0, abs=1e-6), f"{oid} is not plumb"


def test_array_along_curve_tilts_when_upright_is_disabled(engine: FakeEngine) -> None:
    """The wrong behaviour must be reachable, or the plumb test above proves nothing."""
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    rake = [Vec3(0, 0, 0), Vec3(3.0, 0, 1.8)]

    ids = engine.array_along_curve("post", rake, spacing=1.0, keep_upright=False)

    ups = [engine.snapshot(o).transform.rotation.rotate(WORLD_UP) for o in ids]
    assert any(u.z < 0.95 for u in ups), "no instance tilted — the two modes are identical"


def test_array_includes_forced_corner_positions(engine: FakeEngine) -> None:
    """A fixed pitch with no corner-aware resampling produces either a gap or a doubled
    instance at a direction change."""
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    path = [Vec3(0, 0, 0), Vec3(3.0, 0, 0), Vec3(3.0, 2.0, 0)]
    corner = Vec3(3.0, 0, 0)

    ids = engine.array_along_curve(
        "post", path, spacing=1.7, keep_upright=True, extra_points=[corner]
    )

    positions = [engine.snapshot(o).transform.translation for o in ids]
    assert any((p - corner).length() < 1e-6 for p in positions), "no post landed on the corner"


def test_merge_by_distance_welds_coincident_vertices(engine: FakeEngine) -> None:
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(1, 1, 0)]
    engine.create_mesh("m", verts, [(0, 1, 2)])

    outcome = engine.merge_by_distance("m", 1e-6)

    assert outcome.fixed == 1
    assert outcome.complete
    assert engine.snapshot("m").vertex_count == 3


def test_fill_holes_closes_an_open_box(engine: FakeEngine) -> None:
    verts, faces = unit_cube()
    engine.create_mesh("open", verts, faces[:-1])

    outcome = engine.fill_holes("open")

    assert outcome.fixed >= 1
    assert engine.fill_holes("open").fixed == 0, "a second pass found holes the first missed"


def test_fill_holes_reports_what_it_could_not_do(engine: FakeEngine) -> None:
    """A bare count cannot tell "nothing to do" from "found work and refused it" — both
    are zero. A caller would then report a clean mesh that still has a hole in it."""
    verts, faces = unit_cube()
    engine.create_mesh("open", verts, faces[:-1])

    outcome = engine.fill_holes("open", max_sides=3)

    assert outcome.fixed == 0
    assert outcome.skipped >= 1, "the 4-sided hole was skipped but not reported"
    assert not outcome.complete
    assert "max_sides" in outcome.reason


def test_separate_loose_splits_disconnected_shells(engine: FakeEngine) -> None:
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(5, 5, 5), Vec3(6, 5, 5), Vec3(5, 6, 5)]
    engine.create_mesh("two", verts, [(0, 1, 2), (3, 4, 5)])

    parts = engine.separate_loose("two")

    assert len(parts) == 2
    assert not engine.exists("two")


def test_unknown_object_error_names_what_exists(engine: FakeEngine) -> None:
    engine.create_primitive("floor", "plane", Vec3(4, 4, 0))

    with pytest.raises(EngineError) as exc:
        engine.snapshot("flooor")

    assert exc.value.rule == "engine.unknown_object"
    assert "floor" in exc.value.suggestion, "the error should say what does exist"


def test_bake_requires_unwrap_first(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    with pytest.raises(EngineError) as exc:
        engine.bake("box", ["albedo"], 1024, "/tmp")

    assert exc.value.rule == "engine.not_unwrapped"


def test_bake_reports_unavailable_rather_than_failing_obscurely(
    engine_without_bake: FakeEngine,
) -> None:
    """In-process bpy has no windowed context, so bake can legitimately be impossible.
    That must arrive as a named capability failure, not a mystery."""
    engine_without_bake.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine_without_bake.unwrap("box")

    with pytest.raises(EngineUnavailable) as exc:
        engine_without_bake.bake("box", ["albedo"], 1024, "/tmp")

    assert exc.value.capability == "bake"


def test_unwrap_produces_uvs_in_unit_range(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(2, 3, 1))
    engine.unwrap("box")

    uvs = engine.snapshot("box").uvs
    assert uvs is not None and len(uvs) == 8
    assert all(0.0 - 1e-9 <= u <= 1.0 + 1e-9 for uv in uvs for u in uv)


def test_sample_polyline_spaces_along_arc_length_not_chord() -> None:
    path = [Vec3(0, 0, 0), Vec3(3, 0, 0), Vec3(3, 3, 0)]
    pts = sample_polyline(path, 1.0)
    gaps = [(b - a).length() for a, b in zip(pts, pts[1:])]
    # The bend produces one short segment; every other gap is the requested spacing.
    assert sum(1 for g in gaps if abs(g - 1.0) < 1e-6) >= len(gaps) - 2


def test_rotation_from_up_handles_the_antiparallel_case() -> None:
    """A straight-down direction has no unique rotation axis — the naive cross product is
    zero and the maths degenerates. It must still return a valid rotation."""
    q = rotation_from_up_to(Vec3(0, 0, -1))
    result = q.rotate(WORLD_UP)
    assert result.z == pytest.approx(-1.0, abs=1e-9)


def test_quaternion_composition_stays_normalized() -> None:
    q = Quat.identity()
    step = Quat.from_axis_angle(Vec3(0, 0, 1), math.radians(7))
    for _ in range(200):
        q = q * step
    norm = math.sqrt(q.w**2 + q.x**2 + q.y**2 + q.z**2)
    assert norm == pytest.approx(1.0, abs=1e-6), "drift over many small agent edits"


def test_reset_clears_everything(engine: FakeEngine) -> None:
    engine.create_primitive("a", "cube", Vec3(1, 1, 1))
    engine.create_material("m", (0.5, 0.5, 0.5))
    engine.reset()
    assert engine.list_objects() == []


def test_array_uses_the_caller_supplied_name_template(engine: FakeEngine) -> None:
    """Instance ids must be predictable before the call, so an operation can pre-declare
    a constraint per instance and have live re-solve reach individual balusters."""
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


def test_export_carries_the_whole_conversion_not_just_up_axis(engine: FakeEngine) -> None:
    """A left-handed target needs an X mirror AND a rotation-sign flip. Sending one
    without the other is the silent round-trip mirroring bug the profile table exists to
    prevent, so every field must reach the exporter."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    engine.export_gltf(
        ["box"], "out.glb", y_up=True, mirror_x=True, negate_rotation=True, scale=1 / 0.28
    )

    call = next(c for c in reversed(engine.calls) if c[0] == "export_gltf")
    _, path, y_up, mirror_x, negate_rotation, scale = call[1]
    assert (y_up, mirror_x, negate_rotation) == (True, True, True)
    assert scale == pytest.approx(1 / 0.28)
