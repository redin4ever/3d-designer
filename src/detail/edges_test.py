"""Tests for edge selection and bevel-width sizing — the load-bearing tests of this module.

Gate A 1.3 is the user's verbatim deal-breaker: *"Still looks like glued boxes."* Gate A 8.3
chose the heuristic bevel over bevelling every edge specifically because uniform bevelling is
itself an artificiality tell (``docs/decisions/gate-A.md``). Every test below exists to fail
an implementation that quietly reverts to "just bevel everything" or "just use one width" —
the two shortcuts that would make this module technically run without doing its actual job.

Two custom meshes are built by hand below rather than relying on ``testing.unit_cube`` alone,
because a plain axis-aligned box cannot exercise the dihedral-angle or convexity filters in
isolation: every edge of a box has the same 90-degree dihedral angle and is equally convex, so
only the "hidden" filter can tell any of its edges apart. ``_folded_strip`` builds an open
strip of quads, extruded along Y, whose successive segments point at chosen angles in the XZ
plane — the dihedral angle at each interior joint is exactly the difference between
consecutive angles, and the joint is convex when the angle *decreases* from one segment to the
next (derived and checked below against a known-convex box edge; a "roof peak" profile, angle
decreasing through the peak, is the textbook convex case).
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from contracts import Vec3
from detail import EdgeSelection, bevel_width_for, select_bevel_edges
from testing import FakeEngine


def _folded_strip(angles_deg: list[float], *, length: float = 1.0, depth: float = 1.0):
    """Vertices/faces for an open strip of quads extruded along Y.

    Segment ``i`` points at ``angles_deg[i]`` (degrees, measured in the XZ plane from +X).
    The ridge edge at interior joint ``i`` (``1 <= i <= len(angles_deg) - 2``) connects vertex
    ``i`` (bottom, y=0) to vertex ``n + i`` (top, y=depth), where ``n = len(angles_deg) + 1``.
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


# --------------------------------------------------------------------- EdgeSelection itself

def test_edge_selection_is_frozen_and_carries_the_audit_trail() -> None:
    """If this dataclass were mutable, a caller could edit ``reasons`` after the fact and the
    audit trail Gate A 4.2 requires ("what rule it broke") could silently drift from what was
    actually selected — this is real, constructed code, not a stub, so it is checked directly."""
    sel = EdgeSelection(edge_indices=(1, 4), reasons=("sharp convex exposed",), rejected=9)
    assert sel.edge_indices == (1, 4)
    assert sel.rejected == 9
    with pytest.raises(dataclasses.FrozenInstanceError):
        sel.rejected = 0  # type: ignore[misc]


# --------------------------------------------------------------------------- the cube guard

def test_a_plain_cube_selects_a_proper_subset(engine: FakeEngine) -> None:
    """If an implementation selects all twelve edges of a cube, it has silently reverted to
    the blanket bevel the user explicitly rejected (Gate A 1.3, 8.3) — a plain box is the
    simplest input that must still come back as a partial answer, not "bevel everything"."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")

    selection = select_bevel_edges(snap)

    assert len(selection.edge_indices) < len(snap.edges())
    assert selection.rejected > 0


def test_a_plain_cube_hides_its_downward_facing_edges(engine: FakeEngine) -> None:
    """A cube's four bottom edges face away from world up and would not plausibly catch a
    highlight the way its top and vertical edges do; with ``exclude_hidden=False`` those four
    must reappear, proving the flag is not a no-op decoration on this shape."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")

    hidden_excluded = select_bevel_edges(snap, exclude_hidden=True)
    hidden_included = select_bevel_edges(snap, exclude_hidden=False)

    assert len(hidden_included.edge_indices) > len(hidden_excluded.edge_indices)


# ---------------------------------------------------------------------- indices and reasons

def test_every_selected_index_is_a_valid_position_in_edges(engine: FakeEngine) -> None:
    """``MeshSnapshot.edges()`` is the entire contract between a selection made here and the
    edge ``ModifierOps.bevel_edges`` acts on at the engine layer — an out-of-range index would
    silently bevel whichever edge happens to sit there instead, with no error at all."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")
    edge_count = len(snap.edges())

    selection = select_bevel_edges(snap)

    assert selection.edge_indices, "expected at least one selected edge on a cube"
    assert all(0 <= i < edge_count for i in selection.edge_indices)


def test_reasons_is_parallel_to_edge_indices(engine: FakeEngine) -> None:
    """A ``reasons`` list shorter or longer than ``edge_indices`` cannot be zipped against it
    safely — the exact silent-truncation failure ``MeshSnapshot.__post_init__`` already
    guards against for ``normals``, and the same risk applies here for the same reason."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")

    selection = select_bevel_edges(snap)

    assert len(selection.reasons) == len(selection.edge_indices)


# ------------------------------------------------------------------------- dihedral threshold

def test_a_flat_edge_is_rejected_and_a_sharp_edge_is_selected(engine: FakeEngine) -> None:
    """A near-flat joint is exactly the case a bevel would be wasted on — imperceptible, pure
    added triangle cost. Both joints below are built convex and exposed on purpose, so only
    the dihedral-angle filter can be responsible for the difference in outcome."""
    # Segment angles decrease throughout (10 -> 5 -> -80), so both interior joints are convex
    # by this module's own sign convention. Joint 1 (10 -> 5) folds by 5 degrees: well under
    # the default 30-degree threshold. Joint 2 (5 -> -80) folds by 85 degrees: well over it.
    verts, faces = _folded_strip([10.0, 5.0, -80.0])
    engine.create_mesh("strip", verts, faces)
    snap = engine.snapshot("strip")
    edges = snap.edges()
    flat_edge = edges.index((1, 5))
    sharp_edge = edges.index((2, 6))

    selection = select_bevel_edges(snap, min_dihedral_deg=30.0)

    assert flat_edge not in selection.edge_indices
    assert sharp_edge in selection.edge_indices


# ----------------------------------------------------------------------------- convex_only

def test_convex_only_rejects_a_concave_crease_and_including_it_needs_the_flag_off(
    engine: FakeEngine,
) -> None:
    """A concave crease (the inside corner of an open box) is exactly as sharp as an outward
    corner but does not catch a highlight the way one does — Gate A 8.3 asks for edges that
    plausibly would. If ``convex_only=True`` and ``convex_only=False`` select the same thing
    here, the flag does nothing and the concave-exclusion behaviour is not actually wired up."""
    # 0 -> 90 degrees is an *increasing* turn: concave by this module's sign convention (a
    # roof-peak profile, which turns downward through its apex, is the convex case; this is
    # its mirror image, turning upward into a re-entrant corner). 90 degrees clears the
    # default sharpness threshold easily, and both faces have a positive-Z-leaning average
    # normal, so neither the angle filter nor the hidden filter can explain a difference here.
    verts, faces = _folded_strip([0.0, 90.0])
    engine.create_mesh("hinge", verts, faces)
    snap = engine.snapshot("hinge")
    crease_edge = snap.edges().index((1, 4))

    rejected_when_convex_only = select_bevel_edges(snap, convex_only=True)
    included_when_any = select_bevel_edges(snap, convex_only=False)

    assert crease_edge not in rejected_when_convex_only.edge_indices
    assert crease_edge in included_when_any.edge_indices


# --------------------------------------------------------------------------- width scaling

def test_bevel_width_for_a_tiny_object_clamps_to_the_minimum(engine: FakeEngine) -> None:
    """``fraction * size`` for a 1 cm object is a fraction of a millimetre under any
    reasonable definition of "characteristic size" — the width must not go below what the
    engine can even apply (``ModifierOps.bevel_edges`` rejects a non-positive width)."""
    engine.create_primitive("speck", "cube", Vec3(0.01, 0.01, 0.01))
    snap = engine.snapshot("speck")

    width = bevel_width_for(snap, fraction=0.004, minimum=0.0005, maximum=0.01)

    assert width == pytest.approx(0.0005)


def test_bevel_width_for_a_huge_object_clamps_to_the_maximum(engine: FakeEngine) -> None:
    """``fraction * size`` for a 500 m object is metres under any reasonable definition of
    "characteristic size" — without an upper clamp a warehouse-scale object would get a
    grotesquely wide bevel that reads as a modelling error, not a highlight."""
    engine.create_primitive("hangar", "cube", Vec3(500.0, 500.0, 5.0))
    snap = engine.snapshot("hangar")

    width = bevel_width_for(snap, fraction=0.004, minimum=0.0005, maximum=0.01)

    assert width == pytest.approx(0.01)


def test_bevel_width_scales_with_object_size_not_a_fixed_constant(engine: FakeEngine) -> None:
    """The module brief's own example: a 2 mm bevel on a doorknob and the same 2 mm bevel on
    a warehouse are different amounts of wrong. Both objects here land inside
    ``[minimum, maximum]`` for any reasonable size metric, so a genuinely size-scaled result
    must differ between them — a fixed-width implementation would return the same number for
    both and fail this specific assertion even though it might pass the two clamp tests above
    by coincidence."""
    engine.create_primitive("knob", "cube", Vec3(0.2, 0.2, 0.2))
    engine.create_primitive("wall", "cube", Vec3(2.0, 2.0, 0.1))

    width_knob = bevel_width_for(engine.snapshot("knob"))
    width_wall = bevel_width_for(engine.snapshot("wall"))

    assert 0.0005 <= width_knob <= 0.01
    assert 0.0005 <= width_wall <= 0.01
    assert width_knob < width_wall


def test_bevel_width_is_always_positive(engine: FakeEngine) -> None:
    """A width of exactly zero is rejected by ``ModifierOps.bevel_edges`` at the engine layer
    — returning zero here would just move that failure one call later with less information
    attached about which object caused it."""
    engine.create_primitive("speck", "cube", Vec3(0.001, 0.001, 0.001))
    width = bevel_width_for(engine.snapshot("speck"))
    assert width > 0.0
