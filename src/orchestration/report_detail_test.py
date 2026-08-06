"""Tests for what the automatic check actually looks at, and for what the report costs.

Two Gate B findings, both measured against the running product:

- **F-014.** ``_new_problems`` called ``measure.inspect``, whose own docstring says it
  *excludes* the pairwise checks — while every ``ActionReport`` reported
  ``checks_scope: "changed+neighbours"``. A 4 m room produced 39 real clipping defects and
  nothing reported one. The report was not wrong about what it found; it was wrong about
  what it had looked at, which is worse.
- **F-017.** One ``add_railing`` returned ~3,398 tokens listing dimensions and triangle
  count for all 40 objects, and a small room cost ~5,400 tokens of check output. Above
  ``contracts.DETAIL_THRESHOLD`` the report summarises — and has to say that it did, for
  exactly the reason ``checks_skipped`` exists.

Lives beside ``reporting_test.py`` rather than inside it: that file owns cadence, operator
notes and the shape of the report; this one owns what the check examines and what the
report leaves out (Rule 2 — split along a responsibility seam, and keep test files inside
the 450-line budget).
"""

from __future__ import annotations

from contracts import (
    DETAIL_THRESHOLD,
    CheckCadence,
    DefectClass,
    JoineryIntent,
    Operation,
    Phase,
    Transform,
    Vec3,
)
from orchestration import Orchestrator


def _place(scene, object_id: str, x: float, size: float = 1.0) -> None:
    """A unit box centred on the x axis at ``x``. The one geometric primitive these tests
    need — everything below is about which pairs get compared, not about shape."""
    scene.engine.create_primitive(object_id, "cube", Vec3(size, size, size))
    scene.engine.set_transform(object_id, Transform(translation=Vec3(x, 0.0, 0.0)))


def _perform(orch: Orchestrator, produced: tuple[str, ...], op_id: str = "op1", **params):
    lease = orch.current() or orch.acquire("writer", Phase.BLOCKOUT)
    return orch.perform(
        Operation(op_id=op_id, kind="add_cube", produced_objects=produced, params=params),
        lease,
    )


# ------------------------------------------------------------------ F-014: neighbours


def test_the_check_finds_clipping_between_the_changed_object_and_its_neighbour(scene) -> None:
    """The 39-defect miss, as a test. ``measure.inspect`` is a single-object check by
    construction — it cannot see a part interpenetrating a *different* part, which is the
    defect class this product exists to catch and the one an agent cannot see for itself.
    Reporting ``checks_scope="changed+neighbours"`` while running only the single-object
    checks is a report that lies about its own coverage."""
    orch = Orchestrator(scene)
    _place(scene, "wall", 0.0)
    _place(scene, "post", 0.4)  # 0.6 m of overlap: unmistakably interpenetrating

    report = _perform(orch, ("post",))

    clipping = [d for d in report.new_problems if d.defect_class is DefectClass.PART_CLIPPING]
    assert clipping != [], "the neighbour pair was never compared"
    assert {clipping[0].object_id, clipping[0].other_object_id} == {"post", "wall"}
    assert report.checks_scope == "changed+neighbours"


def test_the_check_does_not_sweep_objects_that_are_nowhere_near_the_change(scene) -> None:
    """ADR-011: at thousands of objects a whole-scene pairwise sweep per call is not
    viable, and a report that claims a scope it did not examine cannot be trusted about the
    part it did. Scoping through the spatial index is what makes the check affordable enough
    to run after *every* geometry change — the cadence the user actually asked for."""
    orch = Orchestrator(scene)
    _place(scene, "wall", 0.0)
    _place(scene, "post", 0.4)
    _place(scene, "far_shed", 40.0)

    report = _perform(orch, ("post",))

    assert all("far_shed" not in (d.object_id, d.other_object_id) for d in report.new_problems)


def test_a_declared_joint_is_not_reported_as_clipping(scene) -> None:
    """No library can tell a post socketed into a deck from two posts overlapping — both are
    identical BVH overlaps. Intent is declared, never inferred (``contracts.JoineryIntent``).
    If the neighbour check ignored the operation's declared joinery, every intentional joint
    in a model would come back as a defect and the agent would learn to ignore the whole
    channel."""
    orch = Orchestrator(scene)
    _place(scene, "deck", 0.0)
    _place(scene, "post", 0.4)

    report = _perform(
        orch,
        ("post",),
        op_id="socketed",
    )
    assert any(d.defect_class is DefectClass.PART_CLIPPING for d in report.new_problems)

    lease = orch.current()
    declared = orch.perform(
        Operation(
            op_id="socketed-2",
            kind="add_cube",
            produced_objects=("post",),
            joinery=(JoineryIntent(object_id="post", into_object_id="deck", depth=0.9, axis="x"),),
        ),
        lease,
    )

    assert [d for d in declared.new_problems if d.defect_class is DefectClass.PART_CLIPPING] == []


def test_the_check_finds_a_visual_gap_between_parts_that_should_meet(scene) -> None:
    """A visual gap passes every manifold and watertight check, because each part is
    individually fine — a tread 5 mm short of its stringer is invisible to single-object
    inspection and obvious to a person looking at the render. Missing it is how "verified
    clean" and "visibly broken" end up describing the same model."""
    orch = Orchestrator(scene)
    _place(scene, "stringer", 0.0)
    _place(scene, "tread", 1.005)  # 5 mm short of meeting

    report = _perform(orch, ("tread",))

    gaps = [d for d in report.new_problems if d.defect_class is DefectClass.VISUAL_GAP]
    assert gaps != [], "two parts 5 mm apart were reported as fine"
    assert {gaps[0].object_id, gaps[0].other_object_id} == {"tread", "stringer"}


def test_the_cadence_still_governs_the_neighbour_check(scene) -> None:
    """The neighbour sweep must obey the setting Gate A 3.1 asked for like every other check.
    A check that runs regardless of cadence makes the setting a lie; one that runs and does
    not set ``checks_skipped`` makes "nobody looked" read as "nothing is wrong", which is
    materially worse than not checking at all."""
    orch = Orchestrator(scene, cadence=CheckCadence.ON_REQUEST)
    _place(scene, "wall", 0.0)
    _place(scene, "post", 0.4)

    report = _perform(orch, ("post",))

    assert report.checks_skipped is True
    assert report.new_problems == ()
    assert "not a clean result" in report.render()


# ---------------------------------------------------------------- F-017: report size


def _many(scene, count: int) -> tuple[str, ...]:
    ids = tuple(f"post_{i:02d}" for i in range(count))
    for i, object_id in enumerate(ids):
        _place(scene, object_id, x=i * 4.0)  # far apart: this test is about size, not defects
    return ids


def test_a_large_report_summarises_and_says_that_it_summarised(scene) -> None:
    """Gate B 4.3. Listing dimensions and a triangle count for 40 objects cost ~3,398 tokens
    against ~220 summarised — per call. But a summarised report that does not say it
    summarised reads as a complete one, which is the same failure ``checks_skipped`` exists
    to prevent: the agent believes it has been told everything and never asks."""
    orch = Orchestrator(scene)
    ids = _many(scene, DETAIL_THRESHOLD + 4)

    report = _perform(orch, ids)

    assert report.detail_omitted == len(ids)
    assert report.breakdown != ()
    assert sum(count for _, count in report.breakdown) == len(ids)
    assert report.total_triangles > 0
    assert "describe_object" in report.detail_hint
    assert report.measurements == (), "per-object detail was sent anyway"
    assert "per-object detail omitted" in report.render()


def test_a_small_report_keeps_every_per_object_measurement(scene) -> None:
    """Below the threshold the per-object form is both cheaper than the follow-up call it
    would otherwise force and more useful. Summarising everything would trade one round trip
    for two on the common case — an agent that has to ask for what it always needs is paying
    the token cost twice."""
    orch = Orchestrator(scene)
    ids = _many(scene, 3)

    report = _perform(orch, ids)

    assert report.detail_omitted == 0
    assert report.breakdown == ()
    assert report.detail_hint == ""
    assert len(report.measurements) >= len(ids)


def test_no_defect_is_ever_dropped_to_save_tokens(scene) -> None:
    """The one thing summarising must never touch. A defect the agent is not told about is a
    defect that ships; the whole point of spending tokens on this channel is the problems,
    not the inventory. Gate B 4.3 traded per-object *detail* for size, never findings."""
    orch = Orchestrator(scene)
    count = DETAIL_THRESHOLD + 4
    ids = tuple(f"stack_{i:02d}" for i in range(count))
    for i, object_id in enumerate(ids):
        _place(scene, object_id, x=i * 0.1)  # every neighbour overlaps every other

    report = _perform(orch, ids)

    assert report.detail_omitted == count
    clipping = [d for d in report.new_problems if d.defect_class is DefectClass.PART_CLIPPING]
    assert len(clipping) >= count - 1, (
        f"only {len(clipping)} of at least {count - 1} overlapping pairs were reported"
    )


def test_assumptions_the_tool_made_reach_the_agent(scene) -> None:
    """Gate A 6.4 chose that this tool never carries a table of real-world dimensions — the
    agent supplies every one. Phase 6 found ``add_railing`` quietly defaulting three
    cross-sections to 5cm/5cm/3cm, invisibly, which is a hidden dimension table under another
    name. Gate B 1.4 kept the defaults and required them to be reported; an assumption that
    stops at ``OperationResult`` and never reaches ``ActionReport`` is still invisible."""
    orch = Orchestrator(scene)

    report = _perform(
        orch,
        ("rail",),
        assumptions=("post_size defaulted to 0.05 x 0.05 m", "rail_size defaulted to 0.05 m"),
    )

    assert report.assumptions == (
        "post_size defaulted to 0.05 x 0.05 m",
        "rail_size defaulted to 0.05 m",
    )
    assert "ASSUMED" in report.render()
