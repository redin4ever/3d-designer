"""Tests for ``events.py``: ``subscribe`` and the ``SceneChangeEvent`` delivery contract
(``_emit``, called by ``document.py`` and ``history.py``).

``scene`` never imports ``src/viewer/`` — the dependency arrow points from the viewer into
scene and never back (``contracts.SceneChangeEvent``'s own docstring). The last test in
this file checks that statically, by parsing every source file in this package.
"""

from __future__ import annotations

import ast
from pathlib import Path

from contracts import SceneChangeEvent
from scene import Scene


def test_apply_emits_exactly_one_event_naming_the_new_object_in_highlight(
    engine, handlers, add_cube_op
):
    """The viewer's incremental update path depends on getting exactly one event per
    applied operation with the changed object named in highlight (Gate A 5.3) — zero
    events means a silently stale viewport, and more than one means the operator sees a
    single action reported as several."""
    scene = Scene(engine, handlers)
    events: list[SceneChangeEvent] = []
    scene.subscribe(events.append)

    scene.apply(add_cube_op("op1", "a"))

    assert len(events) == 1
    assert events[0].op_id == "op1"
    assert "a" in events[0].highlight


def test_unsubscribe_stops_further_delivery(engine, handlers, add_cube_op):
    scene = Scene(engine, handlers)
    events: list[SceneChangeEvent] = []
    unsubscribe = scene.subscribe(events.append)
    scene.apply(add_cube_op("op1", "a"))
    assert len(events) == 1

    unsubscribe()
    scene.apply(add_cube_op("op2", "b"))

    assert len(events) == 1, "listener kept receiving events after unsubscribing"


def test_unsubscribe_is_safe_to_call_twice(engine, handlers):
    scene = Scene(engine, handlers)
    unsubscribe = scene.subscribe(lambda event: None)

    unsubscribe()
    unsubscribe()  # must not raise


def test_a_raising_listener_does_not_break_apply(engine, handlers, add_cube_op):
    """The viewer is allowed to crash without taking the geometry core with it — a
    listener that raises must never prevent apply() from completing and returning
    normally."""
    scene = Scene(engine, handlers)
    scene.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("viewer crashed")))

    result = scene.apply(add_cube_op("op1", "a"))

    assert result.ok is True
    assert engine.exists("a")
    assert scene.document.head == 1


def test_other_listeners_still_receive_the_event_when_one_raises(
    engine, handlers, add_cube_op
):
    """A single bad subscriber must not silently starve every other subscriber of an
    event they were promised — one crashing viewer tab must not break live updates for
    every other connected client too."""
    scene = Scene(engine, handlers)
    received: list[SceneChangeEvent] = []
    scene.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    scene.subscribe(received.append)

    scene.apply(add_cube_op("op1", "a"))

    assert len(received) == 1


def test_scene_source_never_imports_the_viewer():
    """Statically checked rather than merely conventional: scene must stay usable,
    disableable and rebuildable independent of the viewer — the whole reason
    ``contracts.SceneChangeEvent`` exists as the sole surface between them."""
    scene_dir = Path(__file__).parent
    source_files = [
        p
        for p in scene_dir.glob("*.py")
        if not p.name.endswith("_test.py") and p.name != "conftest.py"
    ]
    assert source_files, "expected to find scene's own source files next to this test"

    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any("viewer" in n.lower() for n in names), (
                f"{path.name} imports {names!r} — scene must never import viewer"
            )
