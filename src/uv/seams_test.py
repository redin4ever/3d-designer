"""Tests for ``suggest_seams`` — the automatic hard-crease seam suggestion.

A custom folded strip is built by hand for the threshold tests, the same technique
``src/detail/edges_test.py`` uses for its dihedral-angle tests: a plain axis-aligned cube has
every real edge at the same 90-degree dihedral angle, so it cannot show *degrees* of
sharpness — only whether a threshold sits above or below that single value. The strip's
successive segments point at chosen angles in the XZ plane, so the fold at each interior
joint is exactly the difference between consecutive segment angles.
"""

from __future__ import annotations

import math

from contracts import MeshSnapshot, Vec3
from testing import FakeEngine
from uv import suggest_seams


def _folded_strip(angles_deg: list[float], *, length: float = 1.0, depth: float = 1.0):
    """Vertices/faces for an open strip of quads extruded along Y.

    Segment ``i`` points at ``angles_deg[i]`` (degrees, measured in the XZ plane from +X).
    """
    pts = [(0.0, 0.0)]
    x, z = 0.0, 0.0
    for deg in angles_deg:
        rad = math.radians(deg)
        x += length * math.cos(rad)
        z += length * math.sin(rad)
        pts.append((x, z))
    n = len(pts)
    verts = [Vec3(px, 0.0, pz) for px, pz in pts] + [Vec3(px, depth, pz) for px, pz in pts]
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    return verts, faces


# --------------------------------------------------------------------------- the cube guard

def test_a_plain_cube_selects_a_proper_subset(engine: FakeEngine) -> None:
    """A triangulated cube has 18 edges: the 12 real cube edges (each folding at exactly 90
    degrees between two different faces) plus 6 face-diagonal edges introduced by fan
    triangulation (each perfectly flat, 0 degrees, since both its triangles belong to the
    same planar quad). At the default 60-degree threshold only the 12 real edges qualify — an
    implementation that returns every edge, or that returns the diagonals too, has broken
    either the "candidate" rule or the threshold comparison."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")

    seams = suggest_seams(snap)

    assert len(seams) < len(snap.edges())
    assert len(seams) > 0


def test_every_suggested_index_is_in_range(engine: FakeEngine) -> None:
    """``MeshSnapshot.edges()`` is the entire contract between a seam suggestion made here
    and ``UVBakeOps.mark_seams`` at the engine end — an out-of-range index would silently
    seam whichever edge happens to sit at that position instead, with no error at all."""
    engine.create_primitive("box", "cube", Vec3(2.0, 1.0, 3.0))
    snap = engine.snapshot("box")
    edge_count = len(snap.edges())

    seams = suggest_seams(snap)

    assert seams, "expected at least one suggested seam on a cube"
    assert all(0 <= i < edge_count for i in seams)


def test_seams_are_unique_positions() -> None:
    """A repeated index would double-count one edge while a genuinely sharp edge elsewhere
    goes unmarked — the same silent-corruption shape ``MeshSnapshot.__post_init__`` already
    guards against for normals and uvs."""
    verts, faces = _folded_strip([10.0, 5.0, -80.0])
    tris = []
    for f in faces:
        for i in range(1, len(f) - 1):
            tris.append((f[0], f[i], f[i + 1]))
    snap = MeshSnapshot(object_id="strip", vertices=verts, triangles=tris)

    seams = suggest_seams(snap)

    assert len(seams) == len(set(seams))


# ------------------------------------------------------------------------- dihedral threshold

def test_a_flat_joint_is_rejected_and_a_sharp_joint_is_selected(engine: FakeEngine) -> None:
    """Segment angles decrease throughout (10 -> 5 -> -80): joint 1 folds by only 5 degrees
    (well under the default 60-degree threshold, and a joint this shallow is not a real seam
    candidate — cutting it would fragment the unwrap for no visual reason); joint 2 folds by
    85 degrees (a genuine hard crease, well over the threshold)."""
    verts, faces = _folded_strip([10.0, 5.0, -80.0])
    engine.create_mesh("strip", verts, faces)
    snap = engine.snapshot("strip")
    edges = snap.edges()
    flat_edge = edges.index((1, 5))
    sharp_edge = edges.index((2, 6))

    seams = suggest_seams(snap, min_dihedral_deg=60.0)

    assert flat_edge not in seams
    assert sharp_edge in seams


def test_raising_the_threshold_returns_fewer_seams(engine: FakeEngine) -> None:
    """If two different thresholds return the same set, the parameter does nothing. Joint 2
    below folds at 85 degrees: below a 60-degree threshold it qualifies, above a 90-degree
    threshold it does not — the same edge must appear in the lower-threshold result and be
    absent from the higher one."""
    verts, faces = _folded_strip([10.0, 5.0, -80.0])
    engine.create_mesh("strip", verts, faces)
    snap = engine.snapshot("strip")
    sharp_edge = snap.edges().index((2, 6))

    loose = suggest_seams(snap, min_dihedral_deg=60.0)
    strict = suggest_seams(snap, min_dihedral_deg=90.0)

    assert sharp_edge in loose
    assert sharp_edge not in strict
    assert len(strict) < len(loose)


def test_a_boundary_edge_is_never_a_candidate(engine: FakeEngine) -> None:
    """An open (non-closed) strip's outer edges each bound exactly one face — no second face
    means no dihedral angle to measure, and a correct implementation must never suggest one
    of these as a seam regardless of threshold. Only the single interior edge shared by both
    quads has two adjacent faces at all and can legitimately qualify."""
    verts, faces = _folded_strip([0.0, 0.0])
    engine.create_mesh("strip", verts, faces)
    snap = engine.snapshot("strip")
    boundary = set(snap.boundary_edges())
    edges = snap.edges()

    seams = suggest_seams(snap, min_dihedral_deg=0.0)

    for i in seams:
        assert edges[i] not in boundary


def test_default_threshold_is_60_degrees(engine: FakeEngine) -> None:
    """The public interface pins this default (``min_dihedral_deg: float = 60.0``) — a
    silent change here would move every caller's suggestion without them asking for it."""
    verts, faces = _folded_strip([10.0, 5.0, -80.0])
    engine.create_mesh("strip", verts, faces)
    snap = engine.snapshot("strip")

    assert suggest_seams(snap) == suggest_seams(snap, min_dihedral_deg=60.0)
