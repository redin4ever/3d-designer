"""Tests for ``cleanup_bevel_topology`` — the re-triangulation pass, run against an engine.

Split from ``topology_test.py`` for the same reason ``apply.py`` is split from ``edges.py``:
this is the one function in the pairing that *mutates* the engine, and a distinct actor gets
its own file (Rule 2). The decision — which triangles — is tested there; what is tested here
is that running it against a live object is safe, honest about what it did, and declines
rather than destroys when it cannot preserve something.

``FakeEngine.bevel_edges`` never moves a vertex, so nothing here can prove the pass improves
a real bevel. That proof lives in ``bevel_quality_test.py`` against real Blender.
"""

from __future__ import annotations

import pytest

from contracts import EngineError, Vec3
from detail import apply_edge_treatment, cleanup_bevel_topology
from testing import FakeEngine


def _fanned_plate(engine: FakeEngine, object_id: str = "plate") -> str:
    """A 1 m x 4 mm planar face with a 0.8 mm tab at one end.

    ``FakeEngine`` fan-triangulates a face from its first corner, which is what Blender's ear
    clip effectively does to the n-gons a bevel leaves behind — and it puts the tab's two
    vertices in a triangle with a corner 1 m away. That is F-018's shape in miniature, and it
    is what gives the pass below something real to do.
    """
    verts = [
        Vec3(0.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(1.0007, 0.0004, 0.0),
        Vec3(1.0, 0.004, 0.0),
        Vec3(0.0, 0.004, 0.0),
    ]
    return engine.create_mesh(object_id, verts, [(0, 1, 2, 3, 4)])


def test_the_object_keeps_its_id_and_its_place_in_the_scene(engine: FakeEngine) -> None:
    """The cleanup rebuilds the mesh in place. If the object came back under a different id,
    every constraint, joinery intent and operation-log entry naming it would be dangling —
    and the scene document would have no way to know."""
    _fanned_plate(engine)
    before = engine.snapshot("plate")

    cleanup_bevel_topology(engine, "plate")

    assert engine.exists("plate")
    after = engine.snapshot("plate")
    assert after.transform == before.transform
    assert after.world_bounds().size.as_tuple() == pytest.approx(
        before.world_bounds().size.as_tuple()
    )


def test_a_mesh_with_nothing_to_improve_is_reported_as_a_no_op(engine: FakeEngine) -> None:
    """``changed=False`` must mean "looked, found nothing, correctly did nothing" — the same
    contract ``apply_edge_treatment``'s empty selection and ``add_greebles``'s reserved
    surface already hold to. A pass that always claims success trains the calling agent to
    stop checking (Gate A 8.3)."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)]
    faces = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]
    engine.create_mesh("tetra", verts, faces)
    before = engine.snapshot("tetra").triangle_count

    result = cleanup_bevel_topology(engine, "tetra")

    assert result.changed is False
    assert result.triangles_before == result.triangles_after == before
    assert "no" in result.detail.lower()


def test_the_result_names_the_object_and_carries_both_triangle_counts(
    engine: FakeEngine,
) -> None:
    """Gate A 4.1: feedback after any change is what changed plus key measurements. A caller
    reading only ``changed`` cannot tell a re-triangulation that kept the count (the normal
    case) from one that never ran."""
    _fanned_plate(engine)

    result = cleanup_bevel_topology(engine, "plate")

    assert result.object_id == "plate"
    assert result.triangles_before > 0
    assert result.triangles_after > 0


def test_an_unwrapped_object_is_declined_with_a_reason_not_silently_unwrapped(
    engine: FakeEngine,
) -> None:
    """Rebuilding the mesh drops its UV layer, and a silently unwrapped object costs a bake.
    Declining with a stated reason and a next step is the Gate A 4.2 contract; doing it
    quietly is the failure that contract exists to prevent."""
    _fanned_plate(engine)
    engine.unwrap("plate")

    result = cleanup_bevel_topology(engine, "plate")

    assert result.changed is False
    assert "uv" in result.detail.lower()
    assert "before" in result.detail.lower() or "unwrap" in result.detail.lower()


def test_a_single_material_survives_the_rebuild(engine: FakeEngine) -> None:
    """One slot is restorable and must be restored — an object that silently loses its only
    material renders untextured and nothing in the pipeline re-checks materials after the
    detail phase."""
    _fanned_plate(engine)
    mat = engine.create_material("oak", (0.4, 0.3, 0.2))
    engine.assign_material("plate", mat, 0)

    cleanup_bevel_topology(engine, "plate")

    assert engine.snapshot("plate").material_slots == ("oak",)


def test_an_unknown_object_names_the_rule_and_what_exists(engine: FakeEngine) -> None:
    """Gate A 4.2: an agent handed an opaque failure loops on the same call. The engine's own
    ``engine.unknown_object`` error already names what exists; this pass must let it through
    rather than wrapping it in something less useful."""
    with pytest.raises(EngineError):
        cleanup_bevel_topology(engine, "not_here")


# ------------------------------------------------------------- wiring into edge treatment

def test_edge_treatment_runs_the_cleanup_by_default(engine: FakeEngine) -> None:
    """F-018 is only fixed if the fix is on by default — an opt-in quality pass is one an
    unattended agent will never opt into."""
    engine.create_primitive("box", "cube", Vec3(1.0, 2.0, 0.1))

    result = apply_edge_treatment(engine, "box")

    assert "cleanup" in result.detail.lower() or "re-triangulat" in result.detail.lower()


def test_edge_treatment_can_skip_the_cleanup(engine: FakeEngine) -> None:
    """The cleanup is its own step precisely so it can be switched off — for measuring the
    bevel in isolation (``bevel_quality_test.py`` depends on this) and for an object whose
    triangulation the caller wants left exactly as the engine produced it."""
    engine.create_primitive("box", "cube", Vec3(1.0, 2.0, 0.1))

    result = apply_edge_treatment(engine, "box", cleanup=False)

    assert result.changed is True
    assert "cleanup" not in result.detail.lower()


def test_a_bevel_that_did_nothing_does_not_run_a_cleanup_either(engine: FakeEngine) -> None:
    """No bevel, no bevel slivers. Running a mesh rebuild on an object the pass decided not
    to touch would turn a documented no-op into a real mutation."""
    engine.create_primitive("flat", "plane", Vec3(2.0, 2.0, 1.0))
    calls_before = len(engine.calls)

    result = apply_edge_treatment(engine, "flat")

    assert result.changed is False
    assert engine.calls[calls_before:] == []
