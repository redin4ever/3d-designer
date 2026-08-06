"""``get_operator_context`` — what the person watching is pointing at and looking at (Q-03).

Two things reach an agent about the operator, and they travel differently for a reason.

**Focus and annotations ride every ``ActionReport``.** MCP is call/response, so the next tool
response is the only channel into a connected agent's context, and text fits there.

**An image does not.** ``ActionReport`` is a text dataclass and a crop is hundreds of
kilobytes of base64; putting one in a report would cost an agent its whole context for a
single point. So the report says ``image attached (an-1)`` and this tool is what ``an-1``
resolves to. Without it, the "image" half of "text, image or both" is a promise the product
never keeps.

Read-only and lease-less by design: asking what the operator is watching must not require the
ability to change the scene, and a read-only INSPECT sub-agent (ADR-007) is exactly the caller
that needs it most.

Not part of ``mcp_server``'s public barrel — reached through the registry and ``dispatch``.
"""

from __future__ import annotations

from typing import Any

from contracts import ToolError

from .context import needs

__all__ = ["get_operator_context"]


@needs("orchestrator")
def get_operator_context(*, orchestrator: Any, annotation_id: str = "") -> dict[str, Any]:
    """What the operator has marked, and the crop behind one annotation id.

    With no ``annotation_id`` this is the cheap orientation call: what is focused, and which
    images are still available. It never inlines the images themselves — a call whose whole
    job is to say what is available would otherwise cost megabytes, and an agent would stop
    making it.

    With an ``annotation_id`` it returns that one crop.
    """
    focus = list(getattr(orchestrator, "focus", ()) or ())
    held = list(getattr(orchestrator, "held_annotation_images", lambda: ())() or ())

    if not annotation_id:
        return {
            "focus": focus,
            "images": held,
            "hint": (
                f"the operator is watching {len(focus)} object(s); "
                f"{len(held)} annotation image(s) available — "
                "call get_operator_context(annotation_id=...) to see one"
                if (focus or held)
                else "nobody is watching and nothing has been pointed at"
            ),
        }

    image = getattr(orchestrator, "annotation_image", lambda _id: "")(annotation_id) or ""
    if not image:
        # Refused by name rather than returned empty. An agent handed "" would render a
        # broken picture or silently ignore it, and either way would never learn that the
        # thing it was told to look at is gone.
        raise ToolError(
            rule="mcp.unknown_annotation",
            detail=f"no image held for annotation {annotation_id!r}",
            suggestion=(
                f"available: {', '.join(held)}"
                if held
                else "no annotation images are held — images age out as new ones arrive"
            ),
        )

    return {
        "annotation_id": annotation_id,
        "image": image,
        "focus": focus,
        "images": held,
    }
