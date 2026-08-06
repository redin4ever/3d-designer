"""The cross-module pin for geometry primitives that exist in more than one copy.

Three primitives in this codebase are deliberately duplicated rather than imported, because
the modules that need them sit side by side in the dependency graph
(``docs/ARCHITECTURE.md``) and none of them may import another without inverting it:

* ``_triangle_normal`` — four copies: ``align.position``, ``constraints.anchors``,
  ``detail.edges``, ``uv.seams``.
* ``rotation_aligning`` and ``perpendicular_in_plane`` — two copies: ``align._geom`` and
  ``constraints._geom``, documented as byte-identical in ``align/_geom.py``'s own docstring.

Duplication that nothing checks is duplication that drifts, and it already had: three copies
of ``_triangle_normal`` returned ``None`` for a degenerate triangle while the fourth returned
``Vec3(0, 0, 0)`` and leaned on a second, unnamed ``1e-9`` threshold at its call site, so
"make the odd one out match its siblings" was a one-line edit that reintroduced a crash. This
file is what makes that edit fail loudly instead.

**Hosted in ``align`` for ownership reasons, not architectural ones.** ``align`` is the
highest of the three modules the author of this pass may write in, and a test-only import
creates no runtime dependency — ``align`` still depends on ``contracts``/``constraints``/
``measure`` alone at runtime (`.pipeline/modules.json`). ``src/app/`` is the module that
genuinely depends on all four and would be the natural home; moving it there is a
main-agent decision, recorded in ``docs/ASSUMPTIONS.md`` as A-041.
"""

from __future__ import annotations

import math

import pytest

from contracts import EPSILON, MeshSnapshot, Quat, Vec3

from align._geom import (
    perpendicular_in_plane as align_perpendicular_in_plane,
    rotation_aligning as align_rotation_aligning,
)
from align.position import _triangle_normal as align_triangle_normal
from constraints._geom import (
    perpendicular_in_plane as constraints_perpendicular_in_plane,
    rotation_aligning as constraints_rotation_aligning,
)
from constraints.anchors import _face_groups, _triangle_normal as constraints_triangle_normal
from detail.edges import _triangle_normal as detail_triangle_normal
from uv.seams import _triangle_normal as uv_triangle_normal

# --- the four copies, grouped by the question each one is actually answering ---------------

#: The two copies whose job is "does this triangle have a readable orientation at all" —
#: the dihedral-angle proxies in ``detail.edges`` (sharp-edge selection) and ``uv.seams``
#: (hard-crease seam suggestion). Both must accept every triangle a real bevel produces.
MESH_SCALE_COPIES = {
    "detail.edges": detail_triangle_normal,
    "uv.seams": uv_triangle_normal,
}

#: The two copies whose job is "is this triangle part of a face an anchor can name" —
#: face grouping in ``constraints.anchors._face_groups`` and ``align.position._nth_face``.
#: Both must reject a triangle too small to be a face a caller meant to point at.
ANCHOR_SCALE_COPIES = {
    "align.position": align_triangle_normal,
    "constraints.anchors": constraints_triangle_normal,
}

ALL_COPIES = {**MESH_SCALE_COPIES, **ANCHOR_SCALE_COPIES}

#: A well-formed triangle: 1 m x 1 m in the XY plane, cross-product length 1.0, normal +Z.
UNIT_TRIANGLE_VERTS = [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0)]

#: Three colinear points. Cross-product length is exactly 0.0 — there is no direction to
#: return, at any threshold, for any caller.
COLINEAR_VERTS = [Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(2.0, 0.0, 0.0)]

#: A 4 mm x 3 mm corner triangle: cross-product length 1.2e-5. Not invented — measured on
#: real Blender output. A 4 mm bevel (``detail.bevel_width_for`` returns exactly 4 mm for a
#: 1 m object) on a 0.28 x 1.0 x 0.18 m stair tread produces 72 triangles out of 156 whose
#: cross-product length lies in [9.4e-6, 9.3e-5] — every one of them below ``EPSILON``
#: (1e-4) and therefore invisible to any copy that guards on ``EPSILON``. None of them is
#: anywhere near zero area: the smallest genuinely-zero triangle count on that mesh is 0.
BEVEL_CORNER_VERTS = [Vec3(0.0, 0.0, 0.0), Vec3(0.004, 0.0, 0.0), Vec3(0.0, 0.003, 0.0)]

TRIANGLE = (0, 1, 2)


# --- what every copy must agree on ---------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ALL_COPIES))
def test_every_copy_returns_none_for_a_triangle_with_no_orientation(name: str) -> None:
    """One shared answer for "this triangle has no direction": ``None``.

    If the copies encode it differently — one ``None``, one ``Vec3(0, 0, 0)`` — then every
    call site has to know *which* copy it is holding, and "make the odd one out match its
    siblings" becomes a one-line edit that silently changes what its own caller sees. That
    edit already almost happened: the ``constraints`` copy returned a zero vector and its
    caller re-tested it against a second, unnamed threshold, so normalising the return value
    without also fixing the caller would have fed a zero-length 'normal' into
    ``Quat.rotate(...).normalized()`` and crashed anchor resolution on any mesh with a
    sliver in it.
    """
    assert ALL_COPIES[name](COLINEAR_VERTS, TRIANGLE) is None


@pytest.mark.parametrize("name", sorted(ALL_COPIES))
def test_every_copy_agrees_on_a_well_formed_triangle(name: str) -> None:
    """Four copies of one formula must compute one answer.

    A drifted copy does not announce itself: a bevel selection, a seam suggestion and a face
    anchor computed from the same mesh would simply disagree about which way a face points,
    and the product would place things confidently in the wrong orientation.
    """
    normal = ALL_COPIES[name](UNIT_TRIANGLE_VERTS, TRIANGLE)
    assert normal is not None
    assert normal.x == pytest.approx(0.0)
    assert normal.y == pytest.approx(0.0)
    assert normal.z == pytest.approx(1.0)


@pytest.mark.parametrize("name", sorted(ALL_COPIES))
def test_no_copy_ever_returns_a_non_unit_vector(name: str) -> None:
    """A copy returning an unnormalised vector hands its caller a 'normal' it will treat as
    unit — ``acos(dot(n1, n2))`` then reads an angle that is not the dihedral angle, and the
    bevel or seam lands on the wrong edges with no error anywhere.

    ``None`` is the only permitted alternative to a unit vector. This is what makes the
    ``Vec3(0, 0, 0)`` sentinel unrepresentable rather than merely discouraged.
    """
    for verts in (UNIT_TRIANGLE_VERTS, COLINEAR_VERTS, BEVEL_CORNER_VERTS):
        normal = ALL_COPIES[name](verts, TRIANGLE)
        if normal is not None:
            assert normal.length() == pytest.approx(1.0, abs=1e-9)


# --- the one thing they are allowed to disagree about, pinned so it stays deliberate -------


@pytest.mark.parametrize("name", sorted(MESH_SCALE_COPIES))
def test_the_dihedral_proxies_read_a_real_bevel_corner_triangle(name: str) -> None:
    """A 4 mm bevel on a 1 m edge is the product's *default* (``detail.bevel_width_for``
    returns exactly 4 mm there), and it produces corner triangles with a cross-product
    length around 1e-5 — under ``EPSILON`` (1e-4).

    Guarding on ``EPSILON`` therefore discards 46% of the triangles of a freshly bevelled
    stair tread and leaves 144 of its 234 candidate edges unmeasurable, so the sharp-edge
    ratio is computed from 38% of the mesh and reported as if it were the whole. That is a
    wrong number delivered confidently, which is the one failure mode this product exists to
    remove — and it lands hardest on exactly the geometry the detail pass just created.
    """
    normal = MESH_SCALE_COPIES[name](BEVEL_CORNER_VERTS, TRIANGLE)
    assert normal is not None, (
        "a 4 mm x 3 mm bevel-corner triangle is real geometry with a real normal, not a "
        "degenerate sliver"
    )
    assert normal.z == pytest.approx(1.0)


@pytest.mark.parametrize("name", sorted(ANCHOR_SCALE_COPIES))
def test_the_face_group_copies_reject_a_sub_millimetre_sliver(name: str) -> None:
    """The deliberate divergence, stated from the other side.

    ``constraints.anchors._face_groups`` and ``align.position._nth_face`` do not ask "does
    this triangle have an orientation"; they ask "is this a face an agent could have meant".
    Every group they build becomes a selectable face: ``_resolve_face`` falls back to
    ``groups[sorted(groups)[0]]`` for an unrecognised feature name, and
    ``make_coplanar(face=i)`` indexes straight into that same sorted list. Admitting the 72
    bevel-corner triangles a real tread carries would add dozens of 5 mm groups, so
    ``face=0`` would silently become a 5 mm chamfer sliver and a plain
    ``Anchor(kind=FACE)`` could resolve onto one.

    So these two keep the ``EPSILON`` floor **on purpose**, and this test is the reason a
    future reader may not "make all four consistent" by lowering it.
    """
    assert ANCHOR_SCALE_COPIES[name](BEVEL_CORNER_VERTS, TRIANGLE) is None


def test_each_copy_names_its_own_degeneracy_floor() -> None:
    """A bare number in a comparison is a decision nobody can find later.

    The floors here are not the same number and must not be: the dihedral proxies use a
    *numerical* floor (below it there is no representable direction) and the face-group
    copies use a *product* floor (below it there is no face worth anchoring to). Both are
    defensible; neither is discoverable while it is spelled ``1e-4`` inline. Each module
    must export the floor it uses under a name that says which of the two it is.
    """
    from align import position as align_position
    from constraints import anchors as constraints_anchors
    from detail import edges as detail_edges
    from uv import seams as uv_seams

    numerical = {
        "detail.edges": getattr(detail_edges, "DEGENERATE_CROSS_LENGTH", None),
        "uv.seams": getattr(uv_seams, "DEGENERATE_CROSS_LENGTH", None),
    }
    product = {
        "align.position": getattr(align_position, "MIN_ANCHORABLE_FACE_CROSS_LENGTH", None),
        "constraints.anchors": getattr(
            constraints_anchors, "MIN_ANCHORABLE_FACE_CROSS_LENGTH", None
        ),
    }

    assert all(v is not None for v in numerical.values()), (
        f"the dihedral proxies must name their numerical floor: {numerical}"
    )
    assert all(v is not None for v in product.values()), (
        f"the face-group copies must name their product floor: {product}"
    )
    # Copies answering the same question share one value, exactly.
    assert len(set(numerical.values())) == 1, f"the two dihedral proxies have drifted: {numerical}"
    assert len(set(product.values())) == 1, f"the two face-group copies have drifted: {product}"
    # And the two answers are different on purpose — if they ever converge, one of the two
    # rationales above has been quietly dropped and the docstrings are now lying.
    assert set(numerical.values()) != set(product.values())
    assert next(iter(product.values())) == EPSILON
    assert next(iter(numerical.values())) <= 1e-12


def test_face_grouping_never_admits_a_group_without_an_orientation() -> None:
    """``_face_groups`` builds the candidate faces every ``AnchorKind.FACE`` resolves
    against, and each group's stored normal is later fed to
    ``rotation.rotate(normal).normalized()``.

    A group whose normal is a zero vector therefore does not degrade the answer — it raises
    ``ValueError: cannot normalize a zero-length vector`` from inside ``contracts``, with no
    rule and no suggestion, on any mesh that happens to carry a sliver. This is the guard
    that used to be an unexplained ``n.length() < 1e-9`` at the call site; it is a behaviour
    of the module now, not a magic number.
    """
    snapshot = MeshSnapshot(
        object_id="mixed",
        vertices=[
            Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0),  # a real face
            Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 1.0), Vec3(2.0, 0.0, 1.0),  # colinear
        ],
        triangles=[(0, 1, 2), (3, 4, 5)],
    )
    groups = _face_groups(snapshot)

    assert len(groups) == 1, "the colinear triangle must not become an anchorable face"
    for group in groups.values():
        assert group["normal"].length() == pytest.approx(1.0, abs=1e-9)


# --- rotation_aligning / perpendicular_in_plane: the other documented duplication ----------

#: Deterministic, fixed inputs — no randomness, no clock (Rule 4's determinism section).
#: Covers the parallel, antiparallel, oblique and vertical cases each formula branches on.
_DIRECTION_PAIRS = [
    (Vec3(0.0, 1.0, 0.0), Vec3(0.0, 1.0, 0.0)),            # identical
    (Vec3(0.0, 1.0, 0.0), Vec3(0.0, -1.0, 0.0)),           # antiparallel — the flip branch
    (Vec3(0.0, 0.0, 1.0), Vec3(0.0, 0.0, -1.0)),           # antiparallel, |f.x| < 0.9 branch
    (Vec3(1.0, 0.0, 0.0), Vec3(-1.0, 0.0, 0.0)),           # antiparallel, |f.x| >= 0.9 branch
    (Vec3(0.0, 1.0, 0.0), Vec3(0.6, 0.8, 0.0)),            # a 37-degree turn in plan
    (Vec3(0.0, 1.0, 0.0), Vec3(0.0, 0.857, 0.515)),        # a 31-degree stair rake
    (Vec3(0.0, 0.0, 1.0), Vec3(1.0, 1.0, 1.0)),            # oblique, unnormalised input
]

_PERPENDICULAR_INPUTS = [
    Vec3(1.0, 0.0, 0.0),
    Vec3(0.0, 1.0, 0.0),
    Vec3(0.0, 0.0, 1.0),   # vertical — the world-up fallback branch
    Vec3(0.0, 0.0, -1.0),  # vertical the other way
    Vec3(0.6, 0.8, 0.0),
    Vec3(0.0, 0.857, 0.515),
    Vec3(3.0, -4.0, 12.0),
]


def _quats_equal(a: Quat, b: Quat) -> bool:
    return (
        a.w == pytest.approx(b.w, abs=1e-12)
        and a.x == pytest.approx(b.x, abs=1e-12)
        and a.y == pytest.approx(b.y, abs=1e-12)
        and a.z == pytest.approx(b.z, abs=1e-12)
    )


@pytest.mark.parametrize(("source", "target"), _DIRECTION_PAIRS)
def test_both_copies_of_rotation_aligning_return_the_same_quaternion(
    source: Vec3, target: Vec3
) -> None:
    """``align`` and ``constraints`` both build placements; ``align.make_parallel`` composes
    a delta rotation while ``constraints.solve`` reconstructs one from ``up``/``forward``.

    If their shared minimal-rotation formula drifts, the two disagree about where "aligned"
    is, and an object aligned by one and then re-solved by the other moves a little every
    time — the drift shows up as geometry that will not settle rather than as a failure.
    """
    assert _quats_equal(
        align_rotation_aligning(source, target), constraints_rotation_aligning(source, target)
    )


@pytest.mark.parametrize("direction", _PERPENDICULAR_INPUTS)
def test_both_copies_of_perpendicular_in_plane_return_the_same_vector(direction: Vec3) -> None:
    """Any perpendicular satisfies "perpendicular", so these two functions exist only to
    make the choice *repeatable*.

    Two copies choosing differently defeats the entire reason either exists:
    ``make_perpendicular`` and ``ConstraintKind.PERPENDICULAR_TO`` would place the same
    object at two different — both technically correct — orientations, and the operation log
    would not replay to the scene it recorded.
    """
    a = align_perpendicular_in_plane(direction)
    b = constraints_perpendicular_in_plane(direction)
    assert a.x == pytest.approx(b.x, abs=1e-12)
    assert a.y == pytest.approx(b.y, abs=1e-12)
    assert a.z == pytest.approx(b.z, abs=1e-12)


@pytest.mark.parametrize(
    ("copy_name", "call"),
    [
        ("align.rotation_aligning", lambda: align_rotation_aligning(Vec3(), Vec3(0, 0, 1))),
        ("constraints.rotation_aligning", lambda: constraints_rotation_aligning(Vec3(), Vec3(0, 0, 1))),
        ("align.perpendicular_in_plane", lambda: align_perpendicular_in_plane(Vec3())),
        ("constraints.perpendicular_in_plane", lambda: constraints_perpendicular_in_plane(Vec3())),
    ],
)
def test_both_copies_refuse_a_zero_length_direction_by_name(copy_name: str, call) -> None:
    """Gate A 4.2: the agent is told *what rule it broke*.

    A zero-length direction reaching either copy raises ``cannot normalize a zero-length
    vector`` from inside ``contracts.Vec3`` — no rule, no parameter name, no suggestion, and
    nothing above it catches ``ValueError``, so it arrives at the agent as a raw traceback
    from a file it has never seen. An agent handed that retries the identical call.
    """
    from contracts import RuleError

    with pytest.raises(RuleError) as caught:
        call()
    assert caught.value.rule, f"{copy_name} raised a RuleError with no rule"
    assert caught.value.suggestion, f"{copy_name} named a rule but suggested nothing"


def test_the_two_copies_stay_numerically_identical_on_a_composed_round_trip() -> None:
    """The formulas are duplicated on purpose (``align/_geom.py``'s module docstring) — the
    check that keeps that decision honest is that they stay interchangeable.

    Composing a rotation and applying it is where a small formula difference stops being
    small: ``align`` composes its delta onto the object's current rotation, so a divergence
    accumulates across every subsequent align rather than cancelling.
    """
    start = Vec3(0.0, 1.0, 0.0)
    for _, target in _DIRECTION_PAIRS:
        qa = align_rotation_aligning(start, target)
        qc = constraints_rotation_aligning(start, target)
        ra, rc = qa.rotate(start), qc.rotate(start)
        assert (ra - rc).length() < 1e-12
        # and both actually do the job they claim
        expected = target.normalized()
        assert math.isclose(ra.dot(expected), 1.0, abs_tol=1e-9)
