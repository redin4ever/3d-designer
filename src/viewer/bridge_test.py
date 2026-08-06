"""``ViewerBridge``'s lifecycle and scene-event translation: attach/detach, ``seq``,
``full_scene``, ``pending``, and the per-``ChangeKind`` wire mapping.

Client-message routing (``handle_client``) is covered separately in ``client_test.py``.
"""

from __future__ import annotations

from contracts import ChangeKind, SceneChangeEvent, ServerMessageType

from viewer import ViewerBridge


def test_full_scene_includes_every_object_currently_in_the_engine(real_scene, add_cube_op) -> None:
    """``full_scene`` is what a fresh connection gets; an object it misses stays invisible
    until some unrelated later change happens to touch it."""
    real_scene.apply(add_cube_op("op1", "wall_a"))
    real_scene.apply(add_cube_op("op2", "wall_b"))
    bridge = ViewerBridge(real_scene)

    message = bridge.full_scene()

    assert message.type is ServerMessageType.FULL_SCENE
    assert {m.object_id for m in message.meshes} == {"wall_a", "wall_b"}
    assert set(message.object_ids) == {"wall_a", "wall_b"}
    assert {t.object_id for t in message.transforms} == {"wall_a", "wall_b"}


def test_full_scene_on_an_empty_scene_has_no_meshes(real_scene) -> None:
    bridge = ViewerBridge(real_scene)
    message = bridge.full_scene()

    assert message.meshes == ()
    assert message.object_ids == ()


def test_full_resync_event_resends_every_object_currently_in_the_engine(fake_scene, make_snapshot) -> None:
    """FULL_RESYNC is the correctness fallback (ADR-011): "discard everything and
    reload" — it must enumerate the whole scene, not just whatever the triggering event
    happened to name. Here the emitted event carries no object_ids at all, which is
    exactly how the real ``scene.history`` module emits it today."""
    fake_scene.set_objects(make_snapshot("a"), make_snapshot("b"))
    bridge = ViewerBridge(fake_scene)
    bridge.attach()

    fake_scene.publish(SceneChangeEvent(kind=ChangeKind.FULL_RESYNC))

    (message,) = bridge.pending()
    assert message.type is ServerMessageType.FULL_SCENE
    assert {m.object_id for m in message.meshes} == {"a", "b"}


def test_topology_changed_event_resends_mesh_buffers(fake_scene, make_snapshot) -> None:
    """A topology change invalidates cached buffers; the viewer must resend them —
    the correctness path TRANSFORMS_ONLY exists to avoid paying for on every change."""
    snap = make_snapshot("beam")
    fake_scene.set_objects(snap)
    bridge = ViewerBridge(fake_scene)
    bridge.attach()

    fake_scene.publish(
        SceneChangeEvent(kind=ChangeKind.TOPOLOGY_CHANGED, object_ids=("beam",), snapshots=(snap,))
    )

    (message,) = bridge.pending()
    assert message.type is ServerMessageType.MESH_UPSERT
    assert len(message.meshes) == 1
    assert message.meshes[0].object_id == "beam"


def test_transforms_only_event_has_transforms_and_no_mesh_buffers(fake_scene, make_snapshot) -> None:
    """The cheap path (ADR-011) is the entire reason ``ChangeKind.TRANSFORMS_ONLY``
    exists; sending mesh buffers for it defeats the point of having it."""
    snap = make_snapshot("crate")
    fake_scene.set_objects(snap)
    bridge = ViewerBridge(fake_scene)
    bridge.attach()

    fake_scene.publish(
        SceneChangeEvent(kind=ChangeKind.TRANSFORMS_ONLY, object_ids=("crate",), snapshots=(snap,))
    )

    (message,) = bridge.pending()
    assert message.type is ServerMessageType.TRANSFORM_UPDATE
    assert message.meshes == ()
    assert len(message.transforms) == 1
    assert message.transforms[0].object_id == "crate"


def test_seq_is_monotonic_and_assigned_by_the_bridge_not_a_caller(real_scene) -> None:
    """Two messages from one bridge must strictly increase — ``contracts.ServerMessage
    .seq``'s own contract requires exactly one counter, owned here, never a caller."""
    bridge = ViewerBridge(real_scene)

    first = bridge.full_scene()
    second = bridge.full_scene()

    assert first.seq > 0
    assert second.seq > first.seq
    assert bridge.seq == second.seq


def test_seq_increases_across_queued_scene_driven_messages(real_scene, add_cube_op) -> None:
    """Strictly increasing across *every* queued message, not merely across the geometry
    ones. One event now produces several (the mesh, and the ``HIGHLIGHT`` naming what it
    touched); a counter that restarted or repeated between them would have the client
    discard the second as a duplicate under ``wire.py``'s seq rules."""
    bridge = ViewerBridge(real_scene)
    bridge.attach()

    real_scene.apply(add_cube_op("op1", "a"))
    real_scene.apply(add_cube_op("op2", "b"))

    seqs = [m.seq for m in bridge.pending()]
    assert len(seqs) >= 2
    assert seqs == sorted(set(seqs))


def test_detach_really_unsubscribes(real_scene, add_cube_op) -> None:
    """A leaked subscription on every reconnect is a slow memory leak in a long-running
    session — this proves ``detach`` actually removes the listener rather than merely
    forgetting the bridge's own reference to it."""
    bridge = ViewerBridge(real_scene)
    bridge.attach()
    real_scene.apply(add_cube_op("op1", "a"))
    bridge.pending()  # drain what attach produced

    bridge.detach()
    real_scene.apply(add_cube_op("op2", "b"))

    assert bridge.pending() == ()


def test_attach_is_idempotent(real_scene, add_cube_op) -> None:
    """A second ``attach`` must not register a second listener — otherwise every change is
    delivered twice, the viewer draws each mesh twice, and the action log doubles up.

    Compared against a single-attach baseline rather than a hardcoded count. It used to
    assert exactly one message, which was never what this test is about: one scene change
    legitimately produces more than one message now that a mutation also emits ``HIGHLIGHT``
    (Gate A 5.3, "the latest change is highlighted"). Pinning the number here made an
    unrelated feature look like a regression in subscription bookkeeping, and would have
    done so again for ``LOG`` and ``PROBLEMS``. What must hold is that attaching twice
    changes nothing, whatever that number happens to be.
    """
    once = ViewerBridge(real_scene)
    once.attach()
    real_scene.apply(add_cube_op("op1", "a"))
    baseline = len(once.pending())
    assert baseline >= 1, "a scene change produced no messages at all"

    twice = ViewerBridge(real_scene)
    twice.attach()
    twice.attach()  # must not register a second listener
    real_scene.apply(add_cube_op("op2", "b"))

    assert len(twice.pending()) == baseline


def test_a_bridge_whose_queue_raises_does_not_break_scene_apply(real_scene, add_cube_op) -> None:
    """Proves the geometry core survives a broken viewer: ``scene.apply`` must complete
    and record the operation even when the outbound queue itself raises on append."""

    class HostileQueue(list):
        def append(self, item) -> None:
            raise RuntimeError("simulated full/closed transport queue")

    bridge = ViewerBridge(real_scene)
    bridge.attach()
    bridge._queue = HostileQueue()

    result = real_scene.apply(add_cube_op("op1", "a"))

    assert result.ok is True
    assert real_scene.document.head == 1
    assert real_scene.document.operations[0].op_id == "op1"
