"""Named failures for the measurement tool surface.

Gate A 4.2, verbatim: the agent is told *which rule broke* and what to do next. The second
half is the part that is easy to half-keep. ``align.unknown_object`` names its rule
correctly and then answers "what next" by joining every live object id into one string —
at the thousands of objects ADR-011 targets, that is a wall of text an agent cannot act on,
and it costs a round-trip and a context window to discover that.

A near-miss list is the whole fix: an agent that typed ``stair_tred_001`` needs
``stair_tread_001``, not the other 2 999 names.
"""

from __future__ import annotations

import difflib

from contracts import EngineProtocol, ToolError

__all__ = ["require_object", "require_objects", "MAX_SUGGESTIONS"]

#: More than a handful of "did you mean" candidates is the same wall of text in miniature.
MAX_SUGGESTIONS = 5

#: ``difflib``'s similarity floor. 0.6 keeps a one-character typo and rejects an unrelated
#: name; lowering it re-introduces the noise this module exists to remove.
_SIMILARITY = 0.6


def require_object(engine: EngineProtocol, object_id: str, role: str = "object") -> None:
    """Raise :class:`contracts.ToolError` if ``object_id`` is not in the scene.

    ``role`` names the parameter it arrived as (``"a"``, ``"b"``, ``"object_ids[2]"``), so
    an agent that passed three ids learns which one was wrong without bisecting.
    """
    if not isinstance(object_id, str):
        # `mcp_server.validation` checks a parameter's own type but not an array's item
        # types, so `object_ids=[1, 2]` reaches here intact. Naming it is cheap; letting a
        # non-string reach a real bpy lookup is a TypeError several frames down.
        raise ToolError(
            rule="measure.bad_parameters",
            detail=f"{role} must be an object id string, got {type(object_id).__name__}",
            suggestion="pass the id the operation that created the object reported",
        )
    if engine.exists(object_id):
        return

    known = [name for name in engine.list_objects() if isinstance(name, str)]
    close = difflib.get_close_matches(object_id, known, n=MAX_SUGGESTIONS, cutoff=_SIMILARITY)
    if close:
        suggestion = f"did you mean {', '.join(repr(name) for name in close)}? "
    else:
        suggestion = "no live object has a similar name. "
    suggestion += (
        f"{len(known)} objects exist; use the id the operation that created it returned."
    )

    raise ToolError(
        rule="measure.unknown_object",
        detail=f"{role} {object_id!r} does not exist in the scene",
        suggestion=suggestion,
    )


def require_objects(engine: EngineProtocol, object_ids, role: str = "object_ids") -> tuple[str, ...]:
    """Validate a whole id list and return it as a tuple, failing on the first bad entry.

    Also rejects the shapes an agent actually sends by mistake — a bare string instead of a
    list of them, or an empty list — by name, rather than letting ``"wall"`` iterate into
    four one-character object ids that all fail lookup separately.
    """
    if isinstance(object_ids, str):
        raise ToolError(
            rule="measure.bad_parameters",
            detail=f"{role} must be a list of object ids, got the single string {object_ids!r}",
            suggestion=f"pass {role}=[{object_ids!r}]",
        )
    ids = tuple(object_ids or ())
    if not ids:
        raise ToolError(
            rule="measure.bad_parameters",
            detail=f"{role} is empty, so there is nothing to measure",
            suggestion="pass at least one object id",
        )
    for position, object_id in enumerate(ids):
        require_object(engine, object_id, role=f"{role}[{position}]")
    return ids
