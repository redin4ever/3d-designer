"""F-018 — real-Blender bevel topology quality. **These tests need a real bpy.**

``FakeEngine.bevel_edges`` never moves a vertex — it duplicates a face to model polygon
growth — so a bevel-quality assertion written against the fake proves nothing at all. The
defect this file pins down only exists in real geometry, so every test here carries
``@pytest.mark.needs_blender`` and is skipped (loudly, see ``conftest.pytest_report_header``)
on a machine without Blender.

The reviewed defect, measured on a stair tread built exactly as ``ops.add_staircase`` builds
one: **mean triangle aspect ratio ~109 and a worst triangle of 1378:1**. Long thin triangles
shade badly, bake badly and subdivide badly — a mesh can be perfectly valid and still be one
no modeller would accept, which undercuts the single thing the detail pass exists to do
(Gate A 1.3, verbatim: *"Still looks like glued boxes."*).

Where the number comes from, measured rather than assumed: almost none of it is the bevel
itself. It is the *triangulation* of the flat faces the bevel leaves behind — Blender stores
every mesh triangulated (``engine/_shared.py`` invariant #1) and ear-clips the n-gons a bevel
produces, which turns a 1 m x 0.28 m face into needles with a 0.72 mm base and two 992 mm
sides. Those needles carry 47% of the total and are pure waste; the remaining tail is the
bevel strip itself (a 4 mm strip along a 1 m edge is 250:1 and no triangulation can change
that without either a visually wrong bevel width or a triangle-count explosion). So the
cleanup pass attacks the waste and the ceiling below is set to what that actually achieves,
not to what would be nice.
"""

from __future__ import annotations

import pytest

from contracts import Comparison, MetricKind, Vec3
from detail import (
    SLIVER_CEILING,
    apply_edge_treatment,
    bevel_quality_acceptance,
    cleanup_bevel_topology,
    edge_length_uniformity,
    mean_triangle_aspect_ratio,
)

pytestmark = pytest.mark.needs_blender

#: A tread as ``ops.add_staircase`` builds one: run 0.28 m, width 1.0 m, rise 0.18 m.
_TREAD_MIN = Vec3(0.0, -0.5, 0.0)
_TREAD_MAX = Vec3(0.28, 0.5, 0.18)


@pytest.fixture
def blender():
    """A real ``BlenderEngine`` with an empty scene.

    ``engine.create_engine`` is the composition-root factory; nothing outside ``src/engine/``
    may construct ``BlenderEngine`` directly.
    """
    from engine import create_engine

    eng = create_engine()
    eng.reset()
    yield eng
    eng.reset()


def _tread(engine, object_id: str = "tread") -> str:
    x0, y0, z0 = _TREAD_MIN.as_tuple()
    x1, y1, z1 = _TREAD_MAX.as_tuple()
    verts = [
        Vec3(x0, y0, z0), Vec3(x1, y0, z0), Vec3(x1, y1, z0), Vec3(x0, y1, z0),
        Vec3(x0, y0, z1), Vec3(x1, y0, z1), Vec3(x1, y1, z1), Vec3(x0, y1, z1),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    return engine.create_mesh(object_id, verts, faces)


def _is_watertight_manifold(snapshot) -> bool:
    """Every edge bounds exactly two triangles: closed, and no fan of three or more."""
    counts: dict[tuple[int, int], int] = {}
    for tri in snapshot.triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            counts[key] = counts.get(key, 0) + 1
    return bool(counts) and all(c == 2 for c in counts.values())


def _worst_aspect(snapshot) -> float:
    verts = snapshot.world_vertices()
    worst = 0.0
    for tri in snapshot.triangles:
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        lengths = [(b - a).length(), (c - b).length(), (a - c).length()]
        shortest, longest = min(lengths), max(lengths)
        if shortest > 1e-12:
            worst = max(worst, longest / shortest)
    return worst


# ------------------------------------------------------------------ the defect, reproduced

def test_an_untreated_bevel_on_a_stair_tread_is_full_of_slivers(blender) -> None:
    """This is the F-018 measurement itself, kept as a test so the defect cannot silently
    come back by way of a changed default. With the cleanup step switched off, a real bevel
    on a real tread measures far above the ceiling — if this ever stops being true, the
    ceiling below is being met by accident rather than by the cleanup pass, and the number
    the rest of this file reports would be meaningless."""
    _tread(blender)

    apply_edge_treatment(blender, "tread", cleanup=False)

    snapshot = blender.snapshot("tread")
    assert mean_triangle_aspect_ratio(snapshot) > SLIVER_CEILING
    assert _worst_aspect(snapshot) > 1000.0


def test_a_treated_bevel_on_a_stair_tread_stays_under_the_sliver_ceiling(blender) -> None:
    """The deliverable. A bevel that leaves the mesh full of needles is geometry a modeller
    would reject, and it undercuts the one thing the detail pass exists for — an agent
    handed "valid but unusable" has no way to tell the difference from the numbers alone,
    which is exactly why this ceiling is a re-runnable query and not a review note."""
    _tread(blender)

    apply_edge_treatment(blender, "tread")

    snapshot = blender.snapshot("tread")
    assert mean_triangle_aspect_ratio(snapshot) <= SLIVER_CEILING


def test_the_cleanup_removes_the_pathological_needles_not_just_the_average(blender) -> None:
    """A mean can be dragged down while the worst triangle stays catastrophic, and it is the
    worst triangle that produces the visible shading artefact. After the cleanup no triangle
    may be more slivery than the bevel strip geometry itself forces — a 4 mm strip along a
    1 m edge is ~250:1 and cannot be improved without changing the bevel; anything worse than
    that is triangulation waste, and none of it may survive."""
    _tread(blender)

    apply_edge_treatment(blender, "tread")

    assert _worst_aspect(blender.snapshot("tread")) <= 400.0


def test_the_cleanup_improves_the_mesh_it_is_given(blender) -> None:
    """Run as its own step on an already-bevelled object, the cleanup must measurably lower
    the aspect ratio and say so in its result. A cleanup that reports success without moving
    the number is the false-success shape Gate A 4.2 rules out."""
    _tread(blender)
    apply_edge_treatment(blender, "tread", cleanup=False)
    before = mean_triangle_aspect_ratio(blender.snapshot("tread"))

    result = cleanup_bevel_topology(blender, "tread")

    after = mean_triangle_aspect_ratio(blender.snapshot("tread"))
    assert result.changed is True
    assert after < before * 0.8, f"{before:.2f} -> {after:.2f} is not a real improvement"


# ------------------------------------------------------------------ safety: never worse

def test_the_mesh_is_still_manifold_and_watertight_after_the_cleanup(blender) -> None:
    """A cleanup that improves aspect ratio while opening a hole is a worse outcome than the
    slivers: a non-manifold mesh fails on import into an engine or a slicer
    (``DefectClass.NON_MANIFOLD_EDGE`` is a BLOCKER), whereas a slivery one merely looks
    bad."""
    _tread(blender)
    apply_edge_treatment(blender, "tread", cleanup=False)
    assert _is_watertight_manifold(blender.snapshot("tread")), "precondition"

    cleanup_bevel_topology(blender, "tread")

    assert _is_watertight_manifold(blender.snapshot("tread"))


def test_the_cleanup_never_moves_a_vertex_or_changes_the_silhouette(blender) -> None:
    """The cleanup is a re-triangulation, not a repair: it may only change which triangles
    span the same vertices. If it moved a vertex it would be changing the shape the user
    approved, invisibly, under the name of a quality pass."""
    _tread(blender)
    apply_edge_treatment(blender, "tread", cleanup=False)
    before = blender.snapshot("tread")
    before_points = sorted(round(c, 9) for v in before.world_vertices() for c in v.as_tuple())

    cleanup_bevel_topology(blender, "tread")

    after = blender.snapshot("tread")
    assert sorted(round(c, 9) for v in after.world_vertices() for c in v.as_tuple()) == before_points
    assert after.world_bounds().size.as_tuple() == pytest.approx(
        before.world_bounds().size.as_tuple()
    )


def test_a_multi_material_object_is_declined_rather_than_flattened(blender) -> None:
    """Per-triangle material assignment cannot survive a rebuild through
    ``MeshOps.create_mesh``, which takes vertices and faces and nothing else — flattening a
    two-material object to one would be a visible, silent regression.

    This one only exists against real Blender: ``FakeEngine.snapshot`` never populates
    ``triangle_materials``, and ``MeshSnapshot`` refuses a multi-slot snapshot without it, so
    the case cannot even be constructed against the fake.
    """
    _tread(blender)
    blender.assign_material("tread", blender.create_material("oak", (0.4, 0.3, 0.2)), 0)
    blender.assign_material("tread", blender.create_material("steel", (0.6, 0.6, 0.6)), 1)
    apply_edge_treatment(blender, "tread", cleanup=False)

    result = cleanup_bevel_topology(blender, "tread")

    assert result.changed is False
    assert "material" in result.detail.lower()
    assert len(blender.snapshot("tread").material_slots) == 2


def test_a_second_cleanup_finds_nothing_left_to_do(blender) -> None:
    """Idempotence is what makes the pass safe to re-run from a replayed operation log
    (ADR-002). A cleanup that keeps "improving" the same mesh forever would churn geometry
    on every replay and make the log non-deterministic."""
    _tread(blender)
    apply_edge_treatment(blender, "tread")
    first = mean_triangle_aspect_ratio(blender.snapshot("tread"))

    cleanup_bevel_topology(blender, "tread")

    assert mean_triangle_aspect_ratio(blender.snapshot("tread")) == pytest.approx(first)


# ------------------------------------------------------------------ the phase gate

def test_the_acceptance_query_is_a_real_query_that_passes_on_the_treated_tread(
    blender,
) -> None:
    """The detail phase needs something real to check, and another agent is wiring per-phase
    acceptance queries against exactly this. A query naming ``TRIANGLE_ASPECT_RATIO`` with a
    threshold is what lets the gate re-measure the geometry instead of believing an agent
    that says it bevelled something."""
    _tread(blender)
    apply_edge_treatment(blender, "tread")

    query = bevel_quality_acceptance("tread")

    assert query.metric is MetricKind.TRIANGLE_ASPECT_RATIO
    assert query.comparison is Comparison.LTE
    assert query.subject == "tread"
    assert mean_triangle_aspect_ratio(blender.snapshot("tread")) <= query.expected


def test_edge_length_uniformity_is_reported_honestly_before_and_after(blender) -> None:
    """Edge-length spread is reported, not promised: a 4 mm bevel on a 1 m object *is* a
    mesh with a 250:1 spread of edge lengths, and no re-triangulation can change that. This
    test exists so the number stays visible and a later change that quietly makes it much
    worse is caught."""
    _tread(blender)
    apply_edge_treatment(blender, "tread", cleanup=False)
    before = edge_length_uniformity(blender.snapshot("tread"))

    cleanup_bevel_topology(blender, "tread")

    after = edge_length_uniformity(blender.snapshot("tread"))
    assert after <= before * 1.15, f"edge-length uniformity degraded: {before:.3f} -> {after:.3f}"
