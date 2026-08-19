"""Turning one ``contracts.SceneChangeEvent`` into wire messages.

Mixed into ``ViewerBridge`` (``bridge.py``). The one rule every branch here follows:
never let a translation failure — a stale cache entry, an id the engine no longer has —
escape into ``scene``'s call stack. ``_on_scene_change`` is the seam that enforces it.

Nothing here is implemented yet (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import (
    ChangeKind,
    MeshSnapshot,
    SceneChangeEvent,
    ServerMessage,
    ServerMessageType,
)

from .payloads import snapshot_to_payload, transform_payload

__all__ = ["TranslateMixin", "allocate_preview_budgets", "enumerate_object_ids"]

VIEWER_TRIANGLE_BUDGET = 40_000

_BUFFER_KINDS = (ChangeKind.OBJECTS_ADDED, ChangeKind.OBJECTS_MODIFIED, ChangeKind.TOPOLOGY_CHANGED)
_RESYNC_KINDS = (ChangeKind.FULL_RESYNC, ChangeKind.ROLLBACK)


def allocate_preview_budgets(
    snapshots: tuple[MeshSnapshot, ...] | list[MeshSnapshot],
    total_budget: int,
) -> tuple[int, ...]:
    """Allocate a deterministic scene/message budget without starving small meshes."""

    counts = [snapshot.triangle_count for snapshot in snapshots]
    total = sum(counts)
    if total <= total_budget:
        return tuple(counts)
    allocation = [0] * len(counts)
    positive = [index for index, count in enumerate(counts) if count > 0]
    if total_budget <= 0 or not positive:
        return tuple(allocation)
    if total_budget < len(positive):
        ordered = sorted(positive, key=lambda index: snapshots[index].object_id)
        for index in ordered[:total_budget]:
            allocation[index] = 1
        return tuple(allocation)

    for index in positive:
        allocation[index] = 1
    remaining = total_budget - len(positive)
    capacities = [max(0, count - 1) for count in counts]
    capacity_total = sum(capacities)
    if capacity_total == 0:
        return tuple(allocation)
    quotas = [remaining * capacity / capacity_total for capacity in capacities]
    for index, quota in enumerate(quotas):
        allocation[index] += min(capacities[index], int(quota))
    leftover = total_budget - sum(allocation)
    order = sorted(
        positive,
        key=lambda index: (-(quotas[index] - int(quotas[index])), snapshots[index].object_id),
    )
    for index in order:
        if leftover == 0:
            break
        if allocation[index] < counts[index]:
            allocation[index] += 1
            leftover -= 1
    return tuple(allocation)


def _preview_payloads(
    snapshots: tuple[MeshSnapshot, ...] | list[MeshSnapshot],
) -> tuple[tuple, dict[str, object]]:
    budgets = allocate_preview_budgets(snapshots, VIEWER_TRIANGLE_BUDGET)
    meshes = tuple(
        snapshot_to_payload(snapshot, triangle_budget=budget)
        for snapshot, budget in zip(snapshots, budgets, strict=True)
    )
    source_triangles = sum(snapshot.triangle_count for snapshot in snapshots)
    preview_triangles = sum(mesh.triangle_count for mesh in meshes)
    return meshes, {
        "preview": {
            "simplified": preview_triangles < source_triangles,
            "source_triangles": source_triangles,
            "preview_triangles": preview_triangles,
            "budget": VIEWER_TRIANGLE_BUDGET,
        }
    }


def enumerate_object_ids(scene: object) -> tuple[str, ...]:
    """Every object id ``scene`` currently holds.

    ``scene.Scene`` has no public "list every object" method — its interface is the
    operation log and the per-object cache, not an index of what currently exists (a
    filed contract gap; see ``README.md``'s "Assumptions"). Once implemented: prefer a
    public ``list_objects()`` if ``scene`` offers one (test doubles, and any future
    ``scene`` revision), otherwise fall back to the private ``_engine`` attribute
    ``scene.Scene`` already stores, since read-only enumeration cannot corrupt scene's
    invariants and "every object currently in the engine" has to come from somewhere.
    """
    list_objects = getattr(scene, "list_objects", None)
    if callable(list_objects):
        return tuple(list_objects())
    engine = getattr(scene, "_engine", None)
    if engine is not None and hasattr(engine, "list_objects"):
        return tuple(engine.list_objects())
    return ()


class TranslateMixin:
    """Expects ``self._scene``, ``self._next_seq()`` and ``self._enqueue()`` — see
    ``bridge.py``."""

    def _on_scene_change(self, event: SceneChangeEvent) -> None:
        """The listener handed to ``scene.subscribe``. Must never raise — a raising
        listener is already caught individually by ``scene``'s own ``_emit``
        (``events_test.py::test_other_listeners_still_receive_the_event_when_one_raises``),
        but this module does not rely on that alone; see ``bridge.py``'s ``_enqueue``."""
        try:
            messages = self._translate(event)
        except Exception:
            return
        for message in messages:
            self._enqueue(message)

    def _translate(self, event: SceneChangeEvent) -> tuple[ServerMessage, ...]:
        """One ``SceneChangeEvent`` to every wire message it implies, in send order.

        Geometry first, then the two things the event says *about* that geometry. The
        order is load-bearing rather than cosmetic: ``frontend``'s ``applyHighlight``
        looks each id up in the node map it already holds, so a ``HIGHLIGHT`` that
        overtakes the ``MESH_UPSERT`` which created the node marks nothing at all — and
        marks it silently.
        """
        geometry = self._geometry_message(event)
        messages = [] if geometry is None else [geometry]
        messages.extend(self._context_messages(event))
        return tuple(messages)

    def _geometry_message(self, event: SceneChangeEvent) -> ServerMessage | None:
        """Map one ``ChangeKind`` to the one wire message that carries its geometry.

        ``TRANSFORMS_ONLY`` -> ``TRANSFORM_UPDATE`` with transforms only, never mesh
        buffers (the cheap path, ADR-011). ``OBJECTS_ADDED``/``OBJECTS_MODIFIED``/
        ``TOPOLOGY_CHANGED`` -> ``MESH_UPSERT`` with buffers resent. ``OBJECTS_REMOVED``
        -> ``OBJECTS_REMOVED``. ``FULL_RESYNC``/``ROLLBACK`` -> a full-scene resend
        (neither carries reliable per-object ids from the current ``scene``
        implementation — see ``README.md``'s "Assumptions").
        """
        kind = event.kind
        if kind in _BUFFER_KINDS:
            snaps = self._snapshots_for(event)
            meshes, preview_data = _preview_payloads(snaps)
            return ServerMessage(
                type=ServerMessageType.MESH_UPSERT,
                seq=self._next_seq(),
                meshes=meshes,
                transforms=tuple(transform_payload(s) for s in snaps),
                object_ids=event.object_ids,
                data=preview_data,
            )
        if kind is ChangeKind.TRANSFORMS_ONLY:
            snaps = self._snapshots_for(event)
            return ServerMessage(
                type=ServerMessageType.TRANSFORM_UPDATE,
                seq=self._next_seq(),
                transforms=tuple(transform_payload(s) for s in snaps),
                object_ids=event.object_ids,
            )
        if kind is ChangeKind.OBJECTS_REMOVED:
            return ServerMessage(
                type=ServerMessageType.OBJECTS_REMOVED,
                seq=self._next_seq(),
                object_ids=event.object_ids,
            )
        if kind in _RESYNC_KINDS:
            return self._build_full_scene_message()
        if kind is ChangeKind.PHASE_CHANGED and event.phase is not None:
            return ServerMessage(
                type=ServerMessageType.PHASE, seq=self._next_seq(), text=event.phase.value
            )
        return None

    def _context_messages(self, event: SceneChangeEvent) -> list[ServerMessage]:
        """``HIGHLIGHT`` and ``LOG`` from the two fields on the event that nothing read.

        ``scene.apply`` has always set ``highlight`` to what it touched, and
        ``scene.history`` sets ``log_line`` on exactly the rebuilds that did not fully
        complete. Both were being dropped here, which is why "the latest change is
        highlighted" (Gate A 5.3) showed nothing in a real session while both ends of the
        protocol looked fully implemented.

        A ``HIGHLIGHT`` is emitted only when there is something to point at: an empty one
        *clears* the previous highlight (``frontend``'s ``applyHighlight`` replaces the
        set rather than adding to it), so sending one per event would erase the last real
        highlight moments after it appeared.
        """
        messages: list[ServerMessage] = []
        if event.highlight:
            highlight = tuple(event.highlight)
            self._last_highlight = highlight
            messages.append(
                ServerMessage(
                    type=ServerMessageType.HIGHLIGHT,
                    seq=self._next_seq(),
                    object_ids=highlight,
                )
            )
        if event.log_line:
            messages.append(
                ServerMessage(
                    type=ServerMessageType.LOG,
                    seq=self._next_seq(),
                    text=event.log_line,
                    data={"op_id": event.op_id, "head": event.head},
                )
            )
        return messages

    def _snapshots_for(self, event: SceneChangeEvent) -> tuple[MeshSnapshot, ...]:
        """Prefer ``event.snapshots`` if populated; otherwise read through
        ``self._scene.snapshot_of`` for each ``event.object_ids``."""
        if event.snapshots:
            return event.snapshots
        return tuple(self._scene.snapshot_of(oid) for oid in event.object_ids)

    def _build_full_scene_message(self, seq: int | None = None) -> ServerMessage:
        """Every object currently in the engine, as one ``FULL_SCENE`` message.

        ``seq=None`` takes the next number, which is what a resync mid-stream is: a new
        event in the one ordered stream. An explicit ``seq`` is for the greeting a new
        connection gets, which is a *snapshot at* the current point rather than a new
        event — see :meth:`ViewerBridge.greeting`.
        """
        object_ids = enumerate_object_ids(self._scene)
        snapshots = [self._scene.snapshot_of(oid) for oid in object_ids]
        meshes, preview_data = _preview_payloads(snapshots)
        return ServerMessage(
            type=ServerMessageType.FULL_SCENE,
            seq=self._next_seq() if seq is None else seq,
            meshes=meshes,
            transforms=tuple(transform_payload(s) for s in snapshots),
            object_ids=tuple(object_ids),
            data=preview_data,
        )
