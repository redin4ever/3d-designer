"""Tests for ``persistence.py``: ``save``/``load`` (ADR-002's ".blend is a cache, not the
record").

The chosen file format (a single JSON document) is fixed in ``persistence.py``'s module
docstring; the schema-version test below depends on that exact shape to construct a
deliberately-too-new file.
"""

from __future__ import annotations

import json

import pytest

from contracts import SCHEMA_VERSION
from scene import Scene
from testing import FakeEngine


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
