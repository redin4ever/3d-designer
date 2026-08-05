"""Tests for ``SpatialIndex`` — the BVH ADR-011 calls out as a silent-wrong-answer risk.

A broad-phase proximity engine that is slow fails loudly, in a profiler, on the first
heavy scene. One that is *stale* fails silently: it returns a confident, well-formed
answer that happens to be wrong, and every downstream consumer — clipping detection,
scoped re-validation after an edit, the live-view diff — trusts it without a second
check. These tests are written against that failure mode specifically, not against how
the BVH happens to be built inside.

Every test uses the shared ``engine`` fixture from the root ``conftest.py`` and a real
``FakeEngine`` scene — never a mock of ``SpatialIndex``'s own internals — so a passing
suite means the index answers correctly about real geometry, not merely that it was
called correctly.
"""

from __future__ import annotations

import pytest

from contracts import AABB, Transform, Vec3
from spatial import SpatialIndex
from testing import FakeEngine


def _cube(engine: FakeEngine, object_id: str, at: Vec3 = Vec3(0, 0, 0)) -> None:
    """A 1x1x1 cube centred on ``at``. Shared setup so every test's geometry is legible
    from its call site instead of buried in a bespoke vertex list."""
    engine.create_primitive(object_id, "cube", Vec3(1, 1, 1), Transform(translation=at))


# --------------------------------------------------------------------------- empty index

def test_empty_index_answers_every_query_without_raising(engine: FakeEngine) -> None:
    """The index is built before the first object exists in a fresh session and on every
    scene reset. If a query on an empty scene raises, the very first proximity check of a
    run crashes the tool call instead of reporting "nothing nearby"."""
    index = SpatialIndex(engine)
    index.rebuild()

    assert index.pairs_overlapping() == ()
    assert index.in_region(AABB(Vec3(-1, -1, -1), Vec3(1, 1, 1))) == ()
    assert index.neighbours_of(()) == ()
    assert index.size == 0
    assert index.stale_count == 0


# ------------------------------------------------------------------------------- nearby

def test_nearby_finds_an_overlapping_object_and_excludes_itself(engine: FakeEngine) -> None:
    """If ``nearby`` ever includes the subject itself, every object reports clipping with
    its own geometry — a phantom defect on every single object that buries the real ones.
    If it misses a genuine overlap, a real interpenetration ships unreported."""
    _cube(engine, "a")
    _cube(engine, "b", at=Vec3(0.5, 0, 0))
    _cube(engine, "far", at=Vec3(50, 50, 50))
    index = SpatialIndex(engine)
    index.rebuild()

    result = index.nearby("a")

    assert "b" in result
    assert "a" not in result
    assert "far" not in result


def test_nearby_margin_zero_misses_boxes_a_millimetre_apart(engine: FakeEngine) -> None:
    """``margin`` is the entire point of a broad-phase pass: callers deliberately widen the
    search to catch near-misses before a precise check. A margin that does not actually
    widen anything makes every caller relying on it silently under-report proximity."""
    _cube(engine, "a")
    _cube(engine, "b", at=Vec3(1.001, 0, 0))  # 1 mm gap: a.max.x=0.5, b.min.x=0.501
    index = SpatialIndex(engine)
    index.rebuild()

    assert "b" not in index.nearby("a", margin=0.0)


def test_nearby_margin_one_centimetre_finds_boxes_a_millimetre_apart(
    engine: FakeEngine,
) -> None:
    """The other half of the same guarantee: a margin that is requested but not honoured
    is indistinguishable from margin=0 to every caller, and a near-miss that should have
    been flagged for a precise check is never queued for one."""
    _cube(engine, "a")
    _cube(engine, "b", at=Vec3(1.001, 0, 0))
    index = SpatialIndex(engine)
    index.rebuild()

    assert "b" in index.nearby("a", margin=0.01)


# -------------------------------------------------------------------------- invalidation

def test_invalidate_forces_the_next_query_to_read_current_bounds(engine: FakeEngine) -> None:
    """ADR-011's whole reason for direct tests: a stale AABB looks exactly like a correct
    one. If a query after ``invalidate`` can still return the pre-move bounds, every scoped
    re-check that follows an edit is validating geometry that no longer exists."""
    _cube(engine, "a")
    index = SpatialIndex(engine)
    index.rebuild()
    original = index.bounds_of("a")

    engine.set_transform("a", Transform(translation=Vec3(100, 100, 100)))
    moved = engine.world_bounds("a")
    # The index was never told about the move via update()/invalidate() at this point.
    # Whatever it reports must be an honest answer — either the last bounds it knows about,
    # or (for a design with no caching at all) the freshly moved ones — never a third,
    # invented value that matches neither the old nor the new geometry.
    assert index.bounds_of("a") in (original, moved)

    index.invalidate("a")

    assert index.bounds_of("a") == moved, "invalidate() must force a fresh read on next query"


def test_invalidate_makes_a_newly_created_overlap_detectable(engine: FakeEngine) -> None:
    """The concrete failure this module exists to prevent: two objects move together, one
    is invalidated, and the overlap must become visible. A missed overlap here is a false
    negative in the exact broad-phase pass that feeds clipping detection (ADR-005)."""
    _cube(engine, "a", at=Vec3(50, 50, 50))
    _cube(engine, "b")
    index = SpatialIndex(engine)
    index.rebuild()
    assert "a" not in index.nearby("b")

    engine.set_transform("a", Transform(translation=Vec3(0.2, 0, 0)))  # now overlaps b
    index.invalidate("a")

    assert "a" in index.nearby("b"), "a real, newly-created overlap was not reported"


# ---------------------------------------------------------------------------- lifecycle

def test_insert_makes_a_newly_created_object_immediately_queryable(engine: FakeEngine) -> None:
    """Every operation that adds geometry mid-session — a new prop, an array instance —
    relies on ``insert`` alone to make that object visible to proximity checks. If it
    needs a full ``rebuild`` too, the incremental point of the index is lost and every
    caller has to rebuild defensively, at exactly the scale where that is too slow."""
    _cube(engine, "a")
    index = SpatialIndex(engine)
    index.rebuild()
    assert index.size == 1

    _cube(engine, "b", at=Vec3(0.3, 0, 0))
    index.insert("b")

    assert index.size == 2
    assert "b" in index.nearby("a")


def test_update_re_reads_bounds_without_a_separate_invalidate_call(engine: FakeEngine) -> None:
    """``update`` is the call an operation makes right after moving an object. If it does
    not itself force a fresh read, every such call site must also remember to call
    ``invalidate`` — and the one that forgets ships a stale clipping check."""
    _cube(engine, "a")
    _cube(engine, "b", at=Vec3(50, 50, 50))
    index = SpatialIndex(engine)
    index.rebuild()
    assert "b" not in index.nearby("a")

    engine.set_transform("b", Transform(translation=Vec3(0.3, 0, 0)))
    index.update("b")

    assert "b" in index.nearby("a")
    assert index.bounds_of("b") == engine.world_bounds("b")


def test_removed_object_never_reappears_and_bounds_of_names_the_problem(
    engine: FakeEngine,
) -> None:
    """A deleted prop that still shows up in a neighbour query points a repair pass at
    geometry that no longer exists. ``bounds_of`` on a removed id must fail loudly and
    identifiably, not return the last cached box as though the object were still there."""
    _cube(engine, "post_7")
    _cube(engine, "wall_2", at=Vec3(0.3, 0, 0))
    index = SpatialIndex(engine)
    index.rebuild()
    assert "post_7" in index.nearby("wall_2")

    index.remove("post_7")

    assert "post_7" not in index.nearby("wall_2")
    assert all("post_7" not in pair for pair in index.pairs_overlapping())
    with pytest.raises(Exception, match="post_7"):
        index.bounds_of("post_7")


# -------------------------------------------------------------------- aggregate queries

def test_pairs_overlapping_reports_each_pair_once_and_deterministically(
    engine: FakeEngine,
) -> None:
    """A pair reported in both orders double-counts one interpenetration as two defects; a
    non-deterministic order makes a diff between two runs on the same scene look like a
    change even when nothing moved."""
    _cube(engine, "a")
    _cube(engine, "b", at=Vec3(0.3, 0, 0))
    _cube(engine, "c", at=Vec3(50, 50, 50))
    index = SpatialIndex(engine)
    index.rebuild()

    pairs = index.pairs_overlapping()

    assert pairs.count(("a", "b")) + pairs.count(("b", "a")) == 1
    for x, y in pairs:
        assert (y, x) not in pairs, f"{(x, y)} appears in both orders"
        assert x < y, "pair is not canonically ordered — order is not deterministic"
    assert index.pairs_overlapping() == pairs, "ordering changed across an identical rerun"


def test_neighbours_of_includes_inputs_and_their_neighbours_not_distant_objects(
    engine: FakeEngine,
) -> None:
    """This is the scoping primitive ADR-011 requires so validation stays affordable at
    thousands of objects: changed objects plus their neighbours. Missing a neighbour here
    means a real defect next to a changed object is never checked; including a distant,
    unrelated object defeats the whole point of scoping."""
    _cube(engine, "changed")
    _cube(engine, "touching", at=Vec3(0.4, 0, 0))
    _cube(engine, "distant", at=Vec3(200, 200, 200))
    index = SpatialIndex(engine)
    index.rebuild()

    result = index.neighbours_of(["changed"])

    assert "changed" in result
    assert "touching" in result
    assert "distant" not in result


def test_in_region_with_nothing_inside_returns_empty(engine: FakeEngine) -> None:
    """A region query is how the viewer asks "what's in this volume" for a selection box
    or a camera frustum — an empty answer is a routine, common result and must not raise."""
    _cube(engine, "a")
    index = SpatialIndex(engine)
    index.rebuild()

    result = index.in_region(AABB(Vec3(500, 500, 500), Vec3(501, 501, 501)))

    assert result == ()


# -------------------------------------------------------------------------- determinism

def test_repeated_builds_of_the_same_scene_produce_identical_ordering(
    engine: FakeEngine,
) -> None:
    """A live view that re-renders in a different order every reload — with nothing in the
    scene having changed — reads as churn to an operator watching for what actually moved."""
    for i in range(20):
        x, y = (i % 5) * 0.9, (i // 5) * 0.9
        _cube(engine, f"obj_{i:02d}", at=Vec3(x, y, 0))

    first = SpatialIndex(engine)
    first.rebuild()
    second = SpatialIndex(engine)
    second.rebuild()

    assert first.pairs_overlapping() == second.pairs_overlapping()
    assert first.nearby("obj_00") == second.nearby("obj_00")


# --------------------------------------------------------------------------------- scale

def test_pairs_overlapping_matches_a_brute_force_count_at_500_objects(
    engine: FakeEngine,
) -> None:
    """This is a correctness test at district scale, not a benchmark: a broad-phase bug
    that only manifests past a handful of cells ships invisible in every small unit test
    above and only surfaces as missed or phantom clipping on a real level (ADR-011,
    Gate A 11.4). The oracle here is a brute-force O(n^2) scan using the same frozen
    ``AABB.overlaps`` every other module trusts — independent of how the index itself
    prunes its search."""
    cols, rows, pitch = 25, 20, 0.9
    ids = [f"cell_{r:02d}_{c:02d}" for r in range(rows) for c in range(cols)]
    for i, oid in enumerate(ids):
        r, c = divmod(i, cols)
        _cube(engine, oid, at=Vec3(c * pitch, r * pitch, 0))
    assert len(ids) == 500

    index = SpatialIndex(engine)
    index.rebuild()
    pairs = index.pairs_overlapping()

    bounds = {oid: engine.world_bounds(oid) for oid in ids}
    expected = {
        (a, b)
        for i, a in enumerate(ids)
        for b in ids[i + 1 :]
        if bounds[a].overlaps(bounds[b])
    }
    assert set(pairs) == expected
    assert len(pairs) == len(set(pairs)), "a pair was reported more than once"


# ----------------------------------------------------------------------------- degenerate

def test_degenerate_zero_size_bounds_do_not_crash_the_index(engine: FakeEngine) -> None:
    """A prop collapsed onto a single point — zero scale, a bad generator — is a real
    defect the measurement layer needs to see, not a crash that takes down every
    proximity query for the whole scene along with it."""
    _cube(engine, "normal")
    engine.create_primitive("collapsed", "cube", Vec3(0.0, 0.0, 0.0))
    index = SpatialIndex(engine)

    index.rebuild()

    assert index.size == 2
    point = index.bounds_of("collapsed")
    assert point.minimum == point.maximum == Vec3(0, 0, 0)
    assert "collapsed" in index.nearby("normal")
    assert index.pairs_overlapping() != ()
    assert index.in_region(AABB(Vec3(-5, -5, -5), Vec3(5, 5, 5))) != ()
