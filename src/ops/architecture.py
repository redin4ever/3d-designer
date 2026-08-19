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

from contracts import AABB, EPSILON, EngineProtocol, Operation, OperationResult, ToolError, Transform, Vec3

from ._geom import box_mesh, oriented_box_between, vec_component, vec_with_axes
from .validation import validate_params

__all__ = ["add_wall", "add_floor", "add_opening"]


def add_wall(engine: EngineProtocol, op: Operation) -> OperationResult:
    """A straight wall from ``start`` to ``end``, at ``height`` and ``thickness``.

    Required params: ``object_id`` (str), ``start`` (``Vec3``), ``end`` (``Vec3``,
    distinct from ``start``), ``height`` (float, > 0), ``thickness`` (float, > 0).

    Returns ``produced_objects == (wall_id,)``.
    """
    params = validate_params("add_wall", op.params)
    start, end = params["start"], params["end"]
    height, thickness = params["height"], params["thickness"]

    # Lift the centreline so the swept prism's floor sits at start/end's own z, not
    # straddling it — a wall rests on the ground, it isn't centred through it.
    lifted_start = start + Vec3(0.0, 0.0, height / 2.0)
    lifted_end = end + Vec3(0.0, 0.0, height / 2.0)
    verts, faces = oriented_box_between(lifted_start, lifted_end, thickness, height)

    wall_id = engine.create_mesh(params["object_id"], verts, faces)

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(wall_id,))


def add_floor(engine: EngineProtocol, op: Operation) -> OperationResult:
    """A rectangular floor slab, ``width`` x ``depth`` x ``thickness``, centred on
    ``origin`` (default the world origin).

    Required params: ``object_id`` (str), ``width`` (float, > 0), ``depth`` (float, > 0),
    ``thickness`` (float, > 0). Optional: ``origin`` (``Vec3``, default ``Vec3()``).

    Returns ``produced_objects == (floor_id,)``.
    """
    params = validate_params("add_floor", op.params)
    width, depth, thickness = params["width"], params["depth"], params["thickness"]
    origin = params.get("origin", Vec3())

    size = Vec3(width, depth, thickness)
    floor_id = engine.create_primitive(
        params["object_id"], "cube", size, Transform(translation=origin)
    )

    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(floor_id,))


def add_opening(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Boolean a door or window opening out of an existing wall.

    Required params: ``object_id`` (str), ``wall_id`` (str, must already exist),
    ``position`` (float, distance along the wall's own centreline from its start),
    ``width`` (float, > 0), ``height`` (float, > 0). Optional: ``sill_height`` (float,
    >= 0, default 0).

    Raises :class:`~contracts.ToolError` — never silently leaves the wall unmodified —
    when the requested opening does not actually intersect ``wall_id``'s current geometry.

    The wall is rebuilt as the set of box segments that tile its own footprint minus the
    opening (a "picture frame" decomposition around the cut) rather than run through
    ``engine.boolean``: the fake engine's ``difference`` mode only consumes the cutter and
    does not itself alter target topology, so a real volume change has to come from the
    handler. Every segment keeps the wall's own transform, so the result is exactly as
    correctly placed/rotated as the original wall was.

    Returns ``modified_objects == (wall_id,)`` and ``produced_objects == ()``.
    """
    params = validate_params("add_opening", op.params)
    wall_id = params["wall_id"]
    position, width, height = params["position"], params["width"], params["height"]
    sill_height = params.get("sill_height", 0.0)

    if not engine.exists(wall_id):
        raise ToolError(
            "ops.unknown_target",
            f"add_opening: wall {wall_id!r} does not exist",
            "pass the id of a wall already created by add_wall/add_primitive",
        )

    snapshot = engine.snapshot(wall_id)
    transform = snapshot.transform
    local_bounds = AABB.from_points(snapshot.vertices)
    size = local_bounds.size

    length_axis, thickness_axis = ("x", "y") if size.x >= size.y else ("y", "x")
    length_min = vec_component(local_bounds.minimum, length_axis)
    length_max = vec_component(local_bounds.maximum, length_axis)
    z_min, z_max = local_bounds.minimum.z, local_bounds.maximum.z

    a0 = max(length_min, length_min + position - width / 2.0)
    a1 = min(length_max, length_min + position + width / 2.0)
    c0 = max(z_min, z_min + sill_height)
    c1 = min(z_max, z_min + sill_height + height)

    if a0 >= a1 - EPSILON or c0 >= c1 - EPSILON:
        raise ToolError(
            "ops.opening_outside_wall",
            f"add_opening: opening at position={position}, width={width}, height={height}, "
            f"sill_height={sill_height} does not intersect wall {wall_id!r} "
            f"(wall spans {length_max - length_min:.3f}m along its centreline, "
            f"{z_max - z_min:.3f}m tall)",
            f"choose position between 0 and {length_max - length_min:.3f}, or shrink "
            "width/height/sill_height so the opening overlaps the wall",
        )

    b_min = vec_component(local_bounds.minimum, thickness_axis)
    b_max = vec_component(local_bounds.maximum, thickness_axis)

    # The wall's footprint minus the opening rectangle, decomposed into up to four boxes
    # (left / right / below-sill / above-head) — each spans the wall's full thickness.
    # Preserve prior cuts: after one opening the wall is a joined set of disconnected
    # boxes. Subtracting a later opening from the outer AABB would fill the earlier hole.
    adjacency = [set() for _ in snapshot.vertices]
    for tri in snapshot.triangles:
        for left, right in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            adjacency[left].add(right)
            adjacency[right].add(left)
    components = []
    unseen = set(range(len(snapshot.vertices)))
    while unseen:
        seed = unseen.pop()
        component = {seed}
        pending = [seed]
        while pending:
            current = pending.pop()
            for neighbour in adjacency[current] & unseen:
                unseen.remove(neighbour)
                component.add(neighbour)
                pending.append(neighbour)
        components.append(component)

    segments: list[tuple[float, float, float, float, float, float]] = []
    cut_solid = False
    for component in components:
        bounds = AABB.from_points(snapshot.vertices[index] for index in component)
        am = vec_component(bounds.minimum, length_axis)
        ax = vec_component(bounds.maximum, length_axis)
        bm = vec_component(bounds.minimum, thickness_axis)
        bx = vec_component(bounds.maximum, thickness_axis)
        zm, zx = bounds.minimum.z, bounds.maximum.z
        ia0, ia1 = max(am, a0), min(ax, a1)
        ic0, ic1 = max(zm, c0), min(zx, c1)
        if ia0 >= ia1 - EPSILON or ic0 >= ic1 - EPSILON:
            segments.append((am, ax, bm, bx, zm, zx))
            continue
        cut_solid = True
        if ia0 > am + EPSILON:
            segments.append((am, ia0, bm, bx, zm, zx))
        if ia1 < ax - EPSILON:
            segments.append((ia1, ax, bm, bx, zm, zx))
        if ic0 > zm + EPSILON:
            segments.append((ia0, ia1, bm, bx, zm, ic0))
        if ic1 < zx - EPSILON:
            segments.append((ia0, ia1, bm, bx, ic1, zx))
    if not cut_solid:
        raise ToolError(
            "ops.opening_outside_wall",
            f"add_opening: the requested opening intersects no remaining solid region of {wall_id!r}",
            "move the opening away from an existing cut or choose a different wall",
        )
    if not segments:
        # The opening consumes the wall's entire face — keep a sliver so the object
        # remains a valid, non-empty mesh rather than vanishing outright.
        segments.append((length_min, length_min + EPSILON, b_min, b_max, z_min, z_min + EPSILON))

    engine.delete(wall_id)

    def _segment_mesh(a_lo: float, a_hi: float, b_lo: float, b_hi: float, c_lo: float, c_hi: float):
        mins = vec_with_axes(**{length_axis: a_lo, thickness_axis: b_lo, "z": c_lo})
        maxs = vec_with_axes(**{length_axis: a_hi, thickness_axis: b_hi, "z": c_hi})
        return box_mesh(mins, maxs)

    first_verts, first_faces = _segment_mesh(*segments[0])
    new_wall_id = engine.create_mesh(wall_id, first_verts, first_faces, transform)

    extra_ids = []
    for seg in segments[1:]:
        verts, faces = _segment_mesh(*seg)
        extra_ids.append(engine.create_mesh(f"{op.op_id}_wall_part", verts, faces, transform))
    if extra_ids:
        engine.join(new_wall_id, extra_ids)

    return OperationResult(
        op_id=op.op_id, ok=True, produced_objects=(), modified_objects=(new_wall_id,)
    )
