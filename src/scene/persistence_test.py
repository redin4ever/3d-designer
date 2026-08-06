"""Tests for ``persistence.py``: ``save``/``load`` (ADR-002's ".blend is a cache, not the
record").

The chosen file format (a single JSON document) is fixed in ``persistence.py``'s module
docstring; the schema-version test below depends on that exact shape to construct a
deliberately-too-new file.
"""

from __future__ import annotations

import json

import pytest

from contracts import (
    MIN_READABLE_SCHEMA,
    SCHEMA_VERSION,
    AcceptanceQuery,
    Anchor,
    AnchorKind,
    AssetClass,
    Comparison,
    Constraint,
    ConstraintKind,
    ConstraintSet,
    DefectClass,
    JoineryIntent,
    MetricKind,
    Operation,
    Vec3,
)
from scene import Scene
from testing import FakeEngine


def _round_trip(scene: Scene, handlers, tmp_path, name: str = "scene.json") -> Scene:
    """Save and reload through the real file format — the only way to observe what
    persistence actually keeps."""
    path = str(tmp_path / name)
    scene.save(path)
    return Scene.load(path, FakeEngine(), handlers)


def test_save_then_load_round_trips_the_log_head_and_checkpoints(
    engine, handlers, add_cube_op, tmp_path
):
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.apply(add_cube_op("op2", "b"))
    scene.checkpoint("after-two")
    scene.apply(add_cube_op("op3", "c"))
    path = str(tmp_path / "scene.json")

    scene.save(path)
    loaded = Scene.load(path, FakeEngine(), handlers)

    assert len(loaded.document.operations) == len(scene.document.operations) == 3
    assert loaded.document.head == scene.document.head == 3
    assert [c.name for c in loaded.document.checkpoints] == [
        c.name for c in scene.document.checkpoints
    ]


def test_a_loaded_scene_replays_to_identical_geometry(engine, handlers, add_cube_op, tmp_path):
    """A round trip that preserves the log but cannot rebuild the same geometry from it
    is not actually a round trip — the log is supposed to be the whole record (ADR-002)."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    scene.apply(add_cube_op("op2", "b", size=2.0))
    path = str(tmp_path / "scene.json")
    scene.save(path)

    engine2 = FakeEngine()
    loaded = Scene.load(path, engine2, handlers)
    loaded.replay()

    for name in ("a", "b"):
        original, reloaded = engine.snapshot(name), engine2.snapshot(name)
        assert original.vertices == reloaded.vertices
        assert original.triangles == reloaded.triangles


def test_load_of_a_newer_schema_version_fails_loudly(engine, handlers, add_cube_op, tmp_path):
    """A silent misread of a future schema would apply operations or barrier semantics
    this code has never seen and corrupt the scene with no error at all — the one thing
    worse than refusing to open a file is opening it wrong and saying nothing."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    path = tmp_path / "scene.json"
    scene.save(str(path))

    data = json.loads(path.read_text())
    data["schema_version"] = SCHEMA_VERSION + 1
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="schema_version"):
        Scene.load(str(path), FakeEngine(), handlers)


# ------------------------------------------------- the reason the geometry exists (v2)

def _constrained_op() -> Operation:
    """One operation carrying every field v1 dropped, with the nested dataclasses nested
    for real — a `ConstraintSet` holding a `Constraint` holding an `Anchor`."""
    return Operation(
        op_id="op-c",
        kind="add_cube",
        params={"name": "railing", "size": 1.0},
        placements=(
            ConstraintSet(
                object_id="railing",
                constraints=(
                    Constraint(
                        kind=ConstraintKind.FOLLOWS,
                        target=Anchor(
                            kind=AnchorKind.EDGE, object_id="stair_01", feature="outer_edge", index=3
                        ),
                        value=Vec3(0.0, 0.0, 0.9),
                        axis=Vec3(0.0, 0.0, 1.0),
                        tolerance=1e-3,
                        hard=True,
                        params={"note": "handrail height"},
                    ),
                    Constraint(
                        kind=ConstraintKind.CLEAR_OF,
                        target=Anchor(kind=AnchorKind.OBJECT, object_id="wall_n"),
                        value=0.05,
                        hard=False,
                    ),
                ),
                raw_position=Vec3(1.0, 2.0, 3.0),
            ),
        ),
    )


def test_save_and_load_round_trips_the_constraint_set(engine, handlers, tmp_path):
    """ADR-002 chose a parametric document for exactly one payoff: move the stair, and
    the railing constrained to its outer edge follows. v1 dropped `placements` on save, so
    reloading a scene kept the geometry and threw away the reason for it — the railing
    stopped following, silently, with nothing in the file to show it ever had."""
    scene = Scene(engine, handlers)
    scene.apply(_constrained_op())

    loaded = _round_trip(scene, handlers, tmp_path)

    placement = loaded.document.operations[0].placements[0]
    assert placement.object_id == "railing"
    assert placement.raw_position == Vec3(1.0, 2.0, 3.0)
    first, second = placement.constraints
    assert first.kind is ConstraintKind.FOLLOWS
    assert first.target == Anchor(
        kind=AnchorKind.EDGE, object_id="stair_01", feature="outer_edge", index=3
    )
    assert first.value == Vec3(0.0, 0.0, 0.9), "a Vec3 value came back as something else"
    assert first.axis == Vec3(0.0, 0.0, 1.0)
    assert first.tolerance == 1e-3 and first.hard is True
    assert first.params == {"note": "handrail height"}
    assert second.value == 0.05, "a scalar value came back as something else"
    assert second.hard is False
    assert placement.depends_on() == {"stair_01", "wall_n"}, (
        "a reloaded constraint set that cannot name its dependencies cannot re-solve"
    )


def test_save_and_load_round_trips_joinery_intent(engine, handlers, tmp_path):
    """Joinery is *declared design intent* — no library can tell a post socketed 50mm into
    a deck from two posts overlapping by 50mm, because both are the same BVH overlap.
    Losing it on reload turns every intended joint in the scene into a PART_CLIPPING
    defect the agent is then told to go and fix."""
    scene = Scene(engine, handlers)
    scene.apply(
        Operation(
            op_id="op-j",
            kind="add_cube",
            params={"name": "post", "size": 1.0},
            joinery=(
                JoineryIntent(
                    object_id="post",
                    into_object_id="deck",
                    depth=0.15,
                    tolerance=5e-4,
                    reason="post socketed into the deck",
                    axis="z",
                ),
            ),
        )
    )

    loaded = _round_trip(scene, handlers, tmp_path)

    intent = loaded.document.operations[0].joinery[0]
    assert intent == JoineryIntent(
        object_id="post",
        into_object_id="deck",
        depth=0.15,
        tolerance=5e-4,
        reason="post socketed into the deck",
        axis="z",
    )
    assert intent.permits(0.15) and not intent.permits(0.5)


def test_save_and_load_round_trips_acceptance_queries(engine, handlers, tmp_path):
    """An acceptance query is the machine-checkable definition of done, re-run against
    live geometry instead of trusting an agent's claim that it finished (ADR-005, ADR-012).
    A reloaded scene without them has no definition of done left at all — and since
    ADR-012 removed the phase-promotion override, that is the only thing standing between
    an unattended agent and a phase it should not be allowed to leave."""
    scene = Scene(engine, handlers)
    scene.apply(
        Operation(
            op_id="op-a",
            kind="add_cube",
            params={"name": "tread", "size": 1.0},
            acceptance=(
                AcceptanceQuery(
                    query_id="q-manifold",
                    description="no holes in the tread",
                    forbidden_defects=(DefectClass.BOUNDARY_HOLE, DefectClass.NON_MANIFOLD_EDGE),
                    subject="tread",
                ),
                AcceptanceQuery(
                    query_id="q-rise",
                    description="rise is 180mm",
                    metric=MetricKind.DIMENSIONS,
                    subject="tread",
                    expected=0.18,
                    tolerance=1e-3,
                    comparison=Comparison.LTE,
                    params={"axis": "z"},
                ),
            ),
        )
    )

    loaded = _round_trip(scene, handlers, tmp_path)

    manifold, rise = loaded.document.operations[0].acceptance
    assert manifold.forbidden_defects == (
        DefectClass.BOUNDARY_HOLE,
        DefectClass.NON_MANIFOLD_EDGE,
    )
    assert manifold.comparison is Comparison.NONE and manifold.metric is None
    assert rise.metric is MetricKind.DIMENSIONS
    assert rise.comparison is Comparison.LTE
    assert rise.expected == 0.18 and rise.tolerance == 1e-3
    assert rise.params == {"axis": "z"}


def test_save_and_load_round_trips_asset_class_and_proposal_id(engine, handlers, tmp_path):
    """Without `asset_class` the per-class polygon budgets in the export profiles are
    unreachable and only a platform's hard ceiling can ever be checked; without
    `proposal_id` a reloaded scene cannot say which read-only sub-agent's proposal an
    operation came from, so conflict attribution stops working after a reload."""
    scene = Scene(engine, handlers)
    scene.apply(
        Operation(
            op_id="op-p",
            kind="add_cube",
            params={"name": "crate", "size": 1.0},
            asset_class=AssetClass.HERO_PROP,
            proposal_id="prop-42",
        )
    )

    loaded = _round_trip(scene, handlers, tmp_path)

    assert loaded.document.operations[0].asset_class is AssetClass.HERO_PROP
    assert loaded.document.operations[0].proposal_id == "prop-42"


def test_an_operation_with_no_constraints_still_round_trips(engine, handlers, add_cube_op, tmp_path):
    """The empty case is the common one and must not acquire placeholders on the way
    through — an operation that gains an empty `ConstraintSet` it never had would make
    `uses_escape_hatch` and the cycle detector answer questions about geometry nobody
    constrained."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))

    loaded = _round_trip(scene, handlers, tmp_path)

    op = loaded.document.operations[0]
    assert op.placements == () and op.joinery == () and op.acceptance == ()
    assert op.asset_class is None and op.proposal_id == ""


# ------------------------------------------------------------------ reading older files

def test_loading_a_version_1_file_warns_and_names_what_it_lost(
    engine, handlers, add_cube_op, tmp_path
):
    """ADR-015. A v1 file genuinely has no constraints stored, so opening it silently
    reproduces the original bug one layer up: a scene that looks intact and has quietly
    lost the reason for its geometry. It must open — refusing would strand every file
    written before the fix — and it must say what it could not bring."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    path = tmp_path / "v1.json"
    scene.save(str(path))
    data = json.loads(path.read_text())
    data["schema_version"] = 1
    for op in data["operations"]:
        for dropped in ("placements", "joinery", "acceptance", "asset_class", "proposal_id"):
            op.pop(dropped, None)
    path.write_text(json.dumps(data))

    with pytest.warns(UserWarning) as caught:
        loaded = Scene.load(str(path), FakeEngine(), handlers)

    message = str(caught[0].message)
    assert "schema_version 1" in message
    for lost in ("placements", "joinery", "acceptance"):
        assert lost in message, f"the warning never says {lost} was not in the file"
    assert len(loaded.document.operations) == 1
    assert loaded.document.operations[0].placements == ()


def test_loading_a_version_older_than_the_minimum_readable_fails(
    engine, handlers, add_cube_op, tmp_path
):
    """`MIN_READABLE_SCHEMA` is a floor, not decoration. Below it this code has no idea
    what the fields mean, and best-effort guessing is the same silent misread the
    newer-version check already refuses."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    path = tmp_path / "ancient.json"
    scene.save(str(path))
    data = json.loads(path.read_text())
    data["schema_version"] = MIN_READABLE_SCHEMA - 1
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="schema_version"):
        Scene.load(str(path), FakeEngine(), handlers)


def test_a_current_version_file_loads_without_warning(engine, handlers, tmp_path):
    """The warning must be about a real loss, not noise on every open. A warning that
    fires on the normal path is one nobody reads by the time it matters."""
    import warnings

    scene = Scene(engine, handlers)
    scene.apply(_constrained_op())
    path = str(tmp_path / "current.json")
    scene.save(path)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        loaded = Scene.load(path, FakeEngine(), handlers)

    assert loaded.document.schema_version == SCHEMA_VERSION
