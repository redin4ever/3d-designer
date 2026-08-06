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
base64 in one would cost an agent its context for a single point. So the annotation carries a
marker and an id, and the picture waits for the tool that returns it (Q-03).

Nothing here is implemented yet (Rule 4 — tests come first).
"""

from __future__ import annotations

from typing import Any

__all__ = ["AnnotateMixin"]

MAX_HELD_IMAGES = 16
"""How many annotation images are kept. Bounded because these are megabytes each and a long
session points at a lot of things; the agent reads them on its next call or not at all."""


class AnnotateMixin:
    """Expects ``self._scene``, ``self._orchestrator``, ``self._enqueue()`` and
    ``self._next_seq()`` — see ``bridge.py``."""

    def annotation_image(self, annotation_id: str) -> str:
        raise NotImplementedError("viewer.annotation_image: not implemented")

    def _facts_for(self, object_ids: tuple[str, ...]) -> tuple[str, ...]:
        raise NotImplementedError("viewer._facts_for: not implemented")

    def _handle_annotate(self, msg: Any) -> None:
        raise NotImplementedError("viewer._handle_annotate: not implemented")

    def _handle_set_focus(self, msg: Any) -> None:
        raise NotImplementedError("viewer._handle_set_focus: not implemented")

    def _focus_message(self, seq: int | None = None) -> Any:
        raise NotImplementedError("viewer._focus_message: not implemented")
