"""``list_objects`` and ``describe_object`` — what is in the scene, and what one thing in
it actually measures (Gate B 3.1).

Two rules shape both of these, and both come from the stated scale (ADR-011: a full game
district, thousands of objects):

1. **Nothing returns the whole scene.** ``list_objects`` pages and filters. A tool that
   listed every object would cost more tokens at that size than an agent's whole context,
   so the call it needs most is the one it could never afford to make.
2. **No error message inlines the scene either.** A review found a refusal that listed all
   58 live object ids inline — produced, of course, exactly when the agent was already
   lost. ``describe_object`` checks existence itself and refuses with a count and a small
   sample, rather than letting ``EngineProtocol``'s own "known objects: ..." out.

``describe_object`` is also the tool ``contracts.ActionReport.detail_hint`` names by string:
above eight changed objects a report summarises and tells the agent to call this. Keep the
name.

Not part of ``mcp_server``'s public barrel — reached through the registry and ``dispatch``.
"""

from __future__ import annotations

from typing import Any

from contracts import ToolError

from .context import needs
from .serialize import to_jsonable

__all__ = ["list_objects", "describe_object", "DEFAULT_PAGE", "MAX_PAGE"]

DEFAULT_PAGE = 50
"""Objects per call when the agent does not say. Around 50 summaries is a few hundred
tokens — cheap enough to call reflexively, which is the point of an orientation tool."""

MAX_PAGE = 100
"""Hard ceiling on ``limit``. An agent that asks for 5,000 gets 100 and is told there are
more; it does not get to defeat the bound by asking."""

_SAMPLE = 6
"""How many ids a refusal may name. Enough to recognise a naming convention, far short of
enough to reconstruct the scene from an error message."""


def _summarise(engine: Any, object_id: str) -> dict[str, Any]:
    """One compact line per object: what it is called, how big it is, what it costs.

    Dimensions come from ``EngineProtocol.world_bounds`` rather than ``measure.dimensions``
    so that "what is in the scene" keeps working when a measurement module is mid-edit —
    orientation is the call an agent makes *after* something has gone wrong.
    """
    entry: dict[str, Any] = {"object_id": object_id}
    try:
        size = engine.world_bounds(object_id).size
        entry["dimensions"] = [size.x, size.y, size.z]
        entry["triangles"] = engine.snapshot(object_id).triangle_count
    except Exception as exc:  # noqa: BLE001 — one unreadable object must not sink the list
        entry["dimensions"] = None
        entry["triangles"] = None
        entry["unreadable"] = f"{type(exc).__name__}: {exc}"
    return entry


@needs("engine")
def list_objects(
    *, engine: Any, prefix: str = "", limit: int = DEFAULT_PAGE, offset: int = 0
) -> dict[str, Any]:
    """The scene's object ids with a compact summary each, filtered and paged."""
    if limit < 1:
        raise ToolError(
            rule="mcp.invalid_parameter_value",
            detail=f"limit {limit} must be at least 1",
            suggestion=f"omit limit for {DEFAULT_PAGE}, or pass 1..{MAX_PAGE}",
        )
    if offset < 0:
        raise ToolError(
            rule="mcp.invalid_parameter_value",
            detail=f"offset {offset} must not be negative",
            suggestion="omit offset to start at the beginning",
        )

    page = min(limit, MAX_PAGE)
    every = sorted(engine.list_objects())
    matching = [oid for oid in every if oid.startswith(prefix)] if prefix else every
    window = matching[offset : offset + page]
    end = offset + len(window)
    truncated = end < len(matching)

    return {
        "total": len(matching),
        "scene_total": len(every),
        "prefix": prefix,
        "offset": offset,
        "limit": page,
        "returned": len(window),
        "truncated": truncated,
        "next_offset": end if truncated else None,
        "objects": [_summarise(engine, oid) for oid in window],
        "hint": (
            f"showing {offset}-{end} of {len(matching)} — call "
            f"list_objects(offset={end}) for the next page, or pass prefix= to narrow"
            if truncated
            else f"{len(matching)} object(s), all shown"
        ),
    }


def _refuse_unknown(engine: Any, object_id: str) -> ToolError:
    known = sorted(engine.list_objects())
    sample = ", ".join(known[:_SAMPLE])
    more = f" (+{len(known) - _SAMPLE} more)" if len(known) > _SAMPLE else ""
    return ToolError(
        rule="mcp.unknown_object",
        detail=f"no object named {object_id!r}; the scene has {len(known)} object(s)",
        suggestion=(
            f"call list_objects(prefix=...) to find it — e.g. {sample}{more}"
            if known
            else "the scene is empty; create something before describing it"
        ),
    )


@needs("engine")
def describe_object(*, engine: Any, object_id: str) -> dict[str, Any]:
    """Everything about one object: size, cost, placement, and what is wrong with it.

    The counterpart to ``ActionReport``'s summarised form (Gate B 4.3): a report that lists
    40 objects costs ~3,400 tokens, so above the threshold it aggregates and points here.
    If this did not exist, that saving would simply be lost detail.
    """
    if not engine.exists(object_id):
        raise _refuse_unknown(engine, object_id)

    snapshot = engine.snapshot(object_id)
    bounds = engine.world_bounds(object_id)
    size = bounds.size

    defects: list[Any] = []
    defect_note = ""
    try:
        import measure

        defects = list(measure.inspect(engine, object_id))
    except Exception as exc:  # noqa: BLE001 — describing an object must survive a broken check
        defect_note = f"defect scan unavailable: {type(exc).__name__}: {exc}"

    return {
        "object_id": object_id,
        "dimensions": [size.x, size.y, size.z],
        "unit": "m",
        "bounds": {
            "minimum": [bounds.minimum.x, bounds.minimum.y, bounds.minimum.z],
            "maximum": [bounds.maximum.x, bounds.maximum.y, bounds.maximum.z],
        },
        "triangle_count": snapshot.triangle_count,
        "vertex_count": len(snapshot.vertices),
        "polygon_count": snapshot.polygon_count,
        "has_uvs": snapshot.uvs is not None,
        "material_slots": list(snapshot.material_slots),
        "transform": to_jsonable(snapshot.transform),
        "defects": to_jsonable(defects),
        "defect_note": defect_note,
        "summary": (
            f"{object_id}: {size.x:.4g} x {size.y:.4g} x {size.z:.4g} m, "
            f"{snapshot.triangle_count} tris, {len(defects)} defect(s)"
        ),
    }
