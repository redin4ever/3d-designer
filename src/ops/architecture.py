"""``add_wall``, ``add_floor``, ``add_opening`` — the architectural shell operations
blockout starts from.

A wall and a floor are typed parametric operations in their own right (start/end/height/
thickness, width/depth/thickness) rather than a raw box, because a raw box carries no
record of which face is "the thickness" for a later ``flush_with`` or ``on`` constraint to
target. ``add_opening`` is the one REFINE-phase operation in this file: it booleans a door
or window out of an *existing* wall rather than building a new shape, which is why it takes
a ``wall_id`` (a ``target_objects`` reference) instead of its own geometry.
"""

from __future__ import annotations

from contracts import EngineProtocol, Operation, OperationResult

__all__ = ["add_wall", "add_floor", "add_opening"]

_NOT_IMPLEMENTED = "ops.{name}: not implemented"


def add_wall(engine: EngineProtocol, op: Operation) -> OperationResult:
    """A straight wall from ``start`` to ``end``, at ``height`` and ``thickness``.

    Required params: ``object_id`` (str), ``start`` (``Vec3``), ``end`` (``Vec3``,
    distinct from ``start``), ``height`` (float, > 0), ``thickness`` (float, > 0).

    Must call ``validate_params("add_wall", op.params)`` first — a negative height or
    thickness must surface as a named ``ToolError`` before it ever reaches the engine as
    an inverted or degenerate primitive.

    Returns ``produced_objects == (wall_id,)``.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_wall"))


def add_floor(engine: EngineProtocol, op: Operation) -> OperationResult:
    """A rectangular floor slab, ``width`` x ``depth`` x ``thickness``, centred on
    ``origin`` (default the world origin).

    Required params: ``object_id`` (str), ``width`` (float, > 0), ``depth`` (float, > 0),
    ``thickness`` (float, > 0). Optional: ``origin`` (``Vec3``, default ``Vec3()``).

    Returns ``produced_objects == (floor_id,)``.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_floor"))


def add_opening(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Boolean a door or window opening out of an existing wall.

    Required params: ``object_id`` (str — this operation's own record; no new object need
    persist under it, since the boolean cutter is consumed), ``wall_id`` (str, a
    ``target_objects`` entry that must already exist), ``position`` (float, distance in
    metres along the wall's own centreline from its start), ``width`` (float, > 0),
    ``height`` (float, > 0). Optional: ``sill_height`` (float, >= 0, default 0 — a door
    starts at the floor; a window does not).

    Must raise :class:`~contracts.ToolError` — never silently leave the wall unmodified —
    when the requested opening does not actually intersect ``wall_id``'s current world
    bounds. A generator that "succeeds" at cutting nothing leaves an agent believing an
    opening exists where the wall is still solid.

    Returns ``modified_objects == (wall_id,)`` and ``produced_objects == ()`` — the cutter
    used for the boolean is transient and must not persist as a scene object once the
    operation returns.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="add_opening"))
