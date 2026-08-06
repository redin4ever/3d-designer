"""Tests for the neighbour-scoped pairwise checks.

``inspect`` runs every *single-object* check and says so in its own docstring; the two
checks that matter most to a person looking at a build — parts clipping into each other and
joints that visibly do not meet — need a second object and so were reachable only by a
caller that already knew which pairs to ask about. Nothing in the automatic
post-operation loop knew that, so a railing driven through a tread was never reported
until somebody asked by hand. This file covers the helper that closes it.
"""

from __future__ import annotations

import pytest

from contracts import DefectClass, JoineryIntent, ToolError, Transform, Vec3
from measure import neighbour_defects, neighbour_pairs


def _box(engine, object_id: str, size: Vec3, at: Vec3) -> None:
    engine.create_primitive(object_id, "cube", size, Transform(translation=at))


def test_neighbour_defects_finds_clipping_against_an_object_the_caller_never_named(
    engine,
) -> None:
    """The whole point of the helper: the automatic check knows only what an operation
    just touched. If the caller has to supply the other half of every pair, the railing
    that was just placed never gets compared with the tread it clips, and Gate A 4.1's
    'new problems' field is empty exactly when it matters."""
    _box(engine, "deck", Vec3(4, 4, 1), Vec3(0, 0, -0.5))
    _box(engine, "post", Vec3(0.1, 0.1, 2), Vec3(0, 0, 0.5))

    found = neighbour_defects(engine, ["post"])

    clipping = [d for d in found if d.defect_class is DefectClass.PART_CLIPPING]
    assert len(clipping) == 1, found
    assert {clipping[0].object_id, clipping[0].other_object_id} == {"post", "deck"}


def test_neighbour_defects_honours_declared_joinery(engine) -> None:
    """A staircase plus railing reports dozens of clipping defects that are all correct
    joinery. If the helper cannot be told that a post is meant to be 500mm into a deck,
    running it automatically makes the problem list useless and the agent learns to ignore
    it — which is worse than not running it at all."""
    _box(engine, "deck", Vec3(4, 4, 1), Vec3(0, 0, -0.5))
    _box(engine, "post", Vec3(0.1, 0.1, 2), Vec3(0, 0, 0.5))
    intent = JoineryIntent(object_id="post", into_object_id="deck", depth=0.55, axis="z")

    found = neighbour_defects(engine, ["post"], joinery=[intent])

    assert [d for d in found if d.defect_class is DefectClass.PART_CLIPPING] == []


def test_neighbour_defects_reports_a_visual_gap_the_single_object_checks_cannot_see(
    engine,
) -> None:
    """A tread 5mm short of its stringer passes every manifold and watertight check,
    because each part is individually perfect. It is only ever visible pairwise."""
    _box(engine, "a", Vec3(1, 1, 1), Vec3(0, 0, 0))       # ends at x=0.5
    _box(engine, "b", Vec3(1, 1, 1), Vec3(1.005, 0, 0))   # starts at x=0.505

    found = neighbour_defects(engine, ["a"], max_gap=0.01)

    gaps = [d for d in found if d.defect_class is DefectClass.VISUAL_GAP]
    assert len(gaps) == 1, found
    assert gaps[0].magnitude == pytest.approx(0.005, abs=1e-4)


def test_neighbour_defects_ignores_objects_nowhere_near_the_ones_that_changed(
    engine,
) -> None:
    """ADR-011: at thousands of objects a whole-scene pairwise sweep per operation is not
    viable. A helper that quietly compares everything with everything would be correct and
    unusable, and the slowness would show up as the automatic cadence being switched off."""
    _box(engine, "a", Vec3(1, 1, 1), Vec3(0, 0, 0))
    _box(engine, "b", Vec3(1, 1, 1), Vec3(0.97, 0, 0))  # genuinely clips a
    for i in range(200):
        _box(engine, f"far_{i}", Vec3(1, 1, 1), Vec3(100.0 + 2 * i, 0, 0))

    pairs = neighbour_pairs(engine, ["a"])

    assert pairs == (("a", "b"),), pairs


def test_neighbour_pairs_reports_each_pair_once_in_a_stable_order(engine) -> None:
    """Both objects of a clipping pair are usually touched by the same operation. Reporting
    ('a','b') and ('b','a') would double every defect in the problem list, and an unstable
    order would make two identical checks produce two different reports."""
    _box(engine, "a", Vec3(1, 1, 1), Vec3(0, 0, 0))
    _box(engine, "b", Vec3(1, 1, 1), Vec3(0.97, 0, 0))

    assert neighbour_pairs(engine, ["a", "b"]) == (("a", "b"),)
    assert neighbour_pairs(engine, ["b", "a"]) == (("a", "b"),)


def test_an_unknown_object_names_the_rule_and_suggests_near_misses_only(engine) -> None:
    """Gate A 4.2: the agent is told which rule broke and what to do next. It must be a
    *usable* next step — listing every live object id is what `align.unknown_object` does
    today, and at the thousands of objects this product targets that suggestion is a wall
    of text the agent cannot act on."""
    _box(engine, "stair_tread_001", Vec3(1, 1, 1), Vec3(0, 0, 0))
    for i in range(60):
        _box(engine, f"filler_{i:03d}", Vec3(1, 1, 1), Vec3(50.0 + 2 * i, 0, 0))

    with pytest.raises(ToolError) as excinfo:
        neighbour_defects(engine, ["stair_tred_001"])

    error = excinfo.value
    assert error.rule == "measure.unknown_object"
    assert "stair_tread_001" in error.suggestion, error.suggestion
    assert "filler_000" not in error.suggestion, "the whole scene was dumped into a suggestion"
    assert len(error.suggestion) < 400, error.suggestion
