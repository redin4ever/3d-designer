"""Turning a selection into something an agent can act on.

Routing an inbound message is ``client.py``'s job; this is the other half — what a pointed-at
object actually *says*. Split for the reason the rest of this package is split: one file per
responsibility, one class assembled in ``bridge.py``.

Two decisions live here and both are about timing.

**Facts are gathered when the operator points, not when the agent reads them.** The operator
is describing what they were looking at. By the time the annotation rides out on the next tool
response the object may have moved, been rebuilt, or been deleted — and facts gathered then
would describe something the operator never saw, while looking exactly as authoritative.

**The image is held here, not put in the report.** ``ActionReport`` is text, and a megabyte of
base64 in one would cost an agent its whole context for a single point. So the annotation
carries a marker and an id, and the picture waits for the tool that returns it (Q-03).
"""

from __future__ import annotations

from typing import Any

from contracts import (
    AnnotatePayload,
    FocusPayload,
    OperatorAnnotation,
    ServerMessage,
    ServerMessageType,
)

__all__ = ["AnnotateMixin", "MAX_HELD_IMAGES"]

MAX_HELD_IMAGES = 16
"""How many annotation images are kept at once.

Bounded because these are hundreds of kilobytes each and a long session points at a lot of
things. The agent reads an image on its next call or not at all, so the oldest is the one
nobody is coming back for — and an unbounded dict here would grow for the length of a build
that is measured in hours.
"""


class AnnotateMixin:
    """Expects ``self._scene``, ``self._orchestrator``, ``self._enqueue()``,
    ``self._next_seq()``, ``self._images`` and ``self._annotation_seq`` — see ``bridge.py``."""

    def annotation_image(self, annotation_id: str) -> str:
        """The crop attached to one annotation, or ``""`` if there was none or it has aged out.

        Empty rather than raising: an agent asking for a picture that has expired should be
        told there is nothing there, not handed an exception in the middle of a build.
        """
        held = getattr(self._orchestrator, "annotation_image", None)
        if held is not None:
            return held(annotation_id) or ""
        return self._images.get(annotation_id, "")

    def _facts_for(self, object_ids: tuple[str, ...]) -> tuple[str, ...]:
        """One measured line per object, as it is *right now* (Q-02).

        Reads ``EngineProtocol`` rather than ``measure`` so that pointing at something keeps
        working when a measurement module is mid-edit — orientation is the call an operator
        makes *after* something has gone wrong, which is the same reasoning
        ``mcp_server.scene_query._summarise`` gives for the same choice.

        An object that cannot be read still gets a line. Losing the whole annotation over one
        stale id would throw away what the operator typed, at exactly the moment they were
        trying to say something was wrong — and pointing at a thing that has just been deleted
        is a normal way to discover it was deleted.
        """
        engine = getattr(self._scene, "engine", None) or getattr(self._scene, "_engine", None)
        facts: list[str] = []
        for object_id in object_ids:
            if engine is None:
                facts.append(f"{object_id}: no engine attached — nothing could be measured")
                continue
            try:
                size = engine.world_bounds(object_id).size
                snapshot = engine.snapshot(object_id)
                facts.append(
                    f"{object_id}: {size.x:.4g} x {size.y:.4g} x {size.z:.4g} m, "
                    f"{snapshot.triangle_count} tris"
                )
            except Exception as exc:  # noqa: BLE001 — one unreadable object, not a lost message
                facts.append(f"{object_id}: could not be read ({type(exc).__name__})")
        return tuple(facts)

    def _handle_annotate(self, msg: Any) -> None:
        """The operator pointed at something and, usually, said something about it.

        Reaches the agent by the same single route a typed redirect does — riding out on the
        next tool response — because MCP is call/response and there is no other channel into a
        connected agent's context.
        """
        payload = AnnotatePayload(
            object_ids=tuple(msg.data.get("object_ids") or ()),
            text=msg.data.get("text", "") or "",
            image=msg.data.get("image", "") or "",
        )
        if not self._ensure_orchestrator():
            return

        # An edit the operator made with the handles, riding the annotation channel rather
        # than a message type of its own. Q-18 chose "tell the agent, always", so an edit IS
        # something they are telling it about — it belongs in the same ordered stream as the
        # words about it, not in a parallel one that could arrive out of order with them.
        edit = msg.data.get("edit")
        if isinstance(edit, dict) and edit.get("kind"):
            self._apply_operator_edit(edit)

        annotation_id = ""
        if payload.image:
            self._annotation_seq += 1
            annotation_id = f"an-{self._annotation_seq}"
            # Handed to the orchestrator, which is where the MCP tool that returns it can
            # reach — mcp_server gets the orchestrator through context.needs and has no route
            # to this transport. The local dict is only the fallback for a bridge attached to
            # something that does not hold images.
            hold = getattr(self._orchestrator, "hold_annotation_image", None)
            if hold is not None:
                hold(annotation_id, payload.image)
            else:
                self._images[annotation_id] = payload.image
                while len(self._images) > MAX_HELD_IMAGES:
                    self._images.pop(next(iter(self._images)))

        self._orchestrator.add_annotation(
            OperatorAnnotation(
                object_ids=payload.object_ids,
                text=payload.text,
                facts=self._facts_for(payload.object_ids),
                has_image=bool(payload.image),
                annotation_id=annotation_id,
            )
        )

        # Echoed to every watcher for the two reasons _handle_redirect gives: for the sender it
        # is the delivery confirmation the browser reconciles its optimistic line against, and
        # for everybody else it is the point of a shared session (Gate A 10.1).
        said = payload.text or "pointing at " + ", ".join(payload.object_ids)
        if payload.text and payload.object_ids:
            said = f"[{', '.join(payload.object_ids)}] {payload.text}"
        self._enqueue(
            ServerMessage(
                type=ServerMessageType.LOG,
                seq=self._next_seq(),
                text=said,
                data={"role": "operator", "object_ids": list(payload.object_ids)},
            )
        )

    def _apply_operator_edit(self, edit: dict) -> None:
        """Run one hand-made edit through the orchestrator and report what happened.

        The result is enqueued as a LOG rather than swallowed, because Q-21 chose "let me,
        then tell me what broke": a refused edit that produced no message would leave the
        operator watching a part snap back with nothing anywhere saying why.

        An orchestrator with no ``apply_operator_edit`` — an older backend, or a read-only
        viewer — says so instead of raising, keeping the whole message from being lost.
        """
        from contracts import Operation

        apply = getattr(self._orchestrator, "apply_operator_edit", None)
        if apply is None:
            self._enqueue(
                ServerMessage(
                    type=ServerMessageType.ERROR,
                    seq=self._next_seq(),
                    text="this build does not support editing from the browser",
                )
            )
            return

        params = dict(edit.get("params") or {})
        target = params.get("object_id", "")
        self._edit_seq = getattr(self, "_edit_seq", 0) + 1
        report = apply(
            Operation(
                op_id=f"operator-edit-{self._edit_seq}",
                kind=str(edit["kind"]),
                params=params,
                target_objects=(target,) if target else (),
            )
        )

        self._enqueue(
            ServerMessage(
                type=ServerMessageType.LOG,
                seq=self._next_seq(),
                text=(
                    report.summary
                    if report.ok
                    else f"{report.summary}: {report.error_detail or 'refused'}"
                ),
                data={"role": "system", "ok": report.ok},
            )
        )

    def _handle_set_focus(self, msg: Any) -> None:
        """Replace the set of parts the operator is watching (Q-10, Q-11)."""
        payload = FocusPayload(object_ids=tuple(msg.data.get("object_ids") or ()))
        if not self._ensure_orchestrator():
            return
        self._orchestrator.set_focus(payload.object_ids)

        # Echoed even when empty. Suppressing the empty case would leave every other watcher
        # still showing marks that have been taken down, with nothing to correct them.
        self._enqueue(self._focus_message(object_ids=payload.object_ids))

    def _focus_message(self, *, object_ids: tuple[str, ...], seq: int | None = None) -> ServerMessage:
        return ServerMessage(
            type=ServerMessageType.FOCUS,
            seq=self._next_seq() if seq is None else seq,
            object_ids=tuple(object_ids),
        )
