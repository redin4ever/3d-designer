"""``ModifierOps`` — bevel, boolean, array-along-curve and the repair operations.

Every method below prefers ``bpy.data``/``bmesh`` over ``bpy.ops`` (ADR-001); the modifier
stack itself (bevel/boolean/solidify/decimate) is unavoidably ``bpy.ops``-adjacent — a
temporary modifier is added via the data API, then baked and removed immediately by
``_shared.apply_modifier_result`` so nothing ever lingers on the stack (``ModifierOps``
docstring: every mutation here is destructive and immediate). ``array_along_curve`` with
``keep_upright=True`` is the single most behaviourally important method in the whole engine
— see ``ModifierOps.array_along_curve`` in ``src/contracts/engine.py`` and
``conformance.check_array_along_curve_keeps_instances_plumb_on_a_slope``.
"""

from __future__ import annotations

from typing import Sequence

from contracts import EngineError, Quat, RepairOutcome, Transform, Vec3

from ._curve import arc_length_to, rotation_from_up_to, sample_polyline, tangent_at
from ._repair import boundary_loops
from ._shared import (
    apply_modifier_result,
    build_snapshot_topology,
    delete_object,
    edge_lookup_by_original_vertices,
    get_object,
    read_transform_fields,
    write_bmesh,
)

__all__ = ["ModifierOpsMixin"]

_BOOLEAN_MODES = {"union": "UNION", "difference": "DIFFERENCE", "intersect": "INTERSECT"}
#: 'fast' maps to Blender's 'FLOAT' solver identifier — renamed from the historical 'FAST'
#: with no deprecation notice (verified at runtime against this bpy build; ADR-001).
_BOOLEAN_SOLVERS = {"fast": "FLOAT", "exact": "EXACT", "manifold": "MANIFOLD"}


def _resolve_edges(bm, mesh, edge_indices: Sequence[tuple[int, int]]):
    """Translate caller-supplied edges — ``(vertex_a, vertex_b)`` pairs in the UV-split
    vertex numbering a prior ``snapshot(...).edges()`` call returned elements of — back to
    real bmesh edges (invariant #2 in ``_shared.py``). Despite the Protocol's
    ``Sequence[int]`` hint, every conformance check that exercises an explicit selection
    (``check_bevel_edges_with_explicit_selection_increases_triangle_count``,
    ``check_bevel_edges_moves_only_the_selected_edges_geometry``) passes elements straight
    out of ``.edges()`` — i.e. 2-tuples, not positions into that list."""
    _, _, _, orig_of = build_snapshot_topology(mesh)
    lookup = edge_lookup_by_original_vertices(bm.edges)
    resolved = []
    for a, b in edge_indices:
        edge = lookup.get(frozenset((orig_of[a], orig_of[b])))
        if edge is not None:
            resolved.append(edge)
    return resolved


class ModifierOpsMixin:
    """``ModifierOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def bevel_edges(
        self,
        object_id: str,
        width: float,
        segments: int = 2,
        edge_indices: Sequence[int] | None = None,
    ) -> None:
        import bmesh

        obj = get_object(object_id)
        transform = read_transform_fields(obj)
        if transform.has_unapplied_scale():
            raise EngineError(
                "engine.unapplied_scale",
                f"{object_id} has unapplied scale {transform.scale.as_tuple()}",
                "apply scale before bevelling — bevel width is computed in object space, "
                "so an unapplied scale produces uneven bevels",
            )
        if width <= 0:
            raise EngineError("engine.bad_bevel_width", f"width {width} must be positive")

        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()

        selected = list(bm.edges) if edge_indices is None else _resolve_edges(bm, mesh, edge_indices)

        if selected:
            bmesh.ops.bevel(
                bm, geom=selected, offset=width, offset_type="OFFSET", profile=0.5,
                segments=segments, affect="EDGES", clamp_overlap=True,
            )
        write_bmesh(bm, obj)

    def boolean(self, target_id: str, cutter_id: str, mode: str, solver: str = "exact") -> None:
        if mode not in _BOOLEAN_MODES:
            raise EngineError(
                "engine.bad_boolean_mode", f"{mode!r} is not a boolean mode",
                f"use one of: {', '.join(sorted(_BOOLEAN_MODES))}",
            )
        if solver not in _BOOLEAN_SOLVERS:
            raise EngineError(
                "engine.bad_boolean_solver", f"{solver!r} is not a solver",
                f"use one of: {', '.join(sorted(_BOOLEAN_SOLVERS))}",
            )

        target = get_object(target_id)
        cutter = get_object(cutter_id)

        mod = target.modifiers.new(name="engine_boolean", type="BOOLEAN")
        mod.object = cutter
        mod.operation = _BOOLEAN_MODES[mode]
        mod.solver = _BOOLEAN_SOLVERS[solver]
        apply_modifier_result(target, mod)
        delete_object(cutter)

    def solidify(self, object_id: str, thickness: float) -> None:
        if thickness <= 0:
            raise EngineError("engine.bad_thickness", f"thickness {thickness} must be positive")
        obj = get_object(object_id)
        mod = obj.modifiers.new(name="engine_solidify", type="SOLIDIFY")
        mod.thickness = thickness
        apply_modifier_result(obj, mod)

    def array_along_curve(
        self,
        object_id: str,
        curve_points: Sequence[Vec3],
        spacing: float,
        *,
        keep_upright: bool,
        extra_points: Sequence[Vec3] = (),
        name_template: str = "{base}_i{index:03d}",
    ) -> list[str]:
        if spacing <= 0:
            raise EngineError("engine.bad_spacing", f"spacing {spacing} must be positive")
        if len(curve_points) < 2:
            raise EngineError(
                "engine.short_curve", "a curve needs at least two points",
                "pass the path's start and end at minimum",
            )

        positions = sample_polyline(curve_points, spacing)
        for p in extra_points:
            if all((p - q).length() > 1e-6 for q in positions):
                positions.append(p)
        positions.sort(key=lambda p: arc_length_to(curve_points, p))

        produced: list[str] = []
        for i, pos in enumerate(positions):
            rot = Quat.identity()
            if not keep_upright:
                rot = rotation_from_up_to(tangent_at(curve_points, pos))
            new_id = name_template.format(base=object_id, index=i)
            produced.append(
                self.duplicate(object_id, new_id, Transform(translation=pos, rotation=rot))
            )
        return produced

    def decimate(self, object_id: str, ratio: float) -> None:
        if not 0 < ratio <= 1:
            raise EngineError("engine.bad_ratio", f"ratio {ratio} must be in (0, 1]")
        obj = get_object(object_id)
        mod = obj.modifiers.new(name="engine_decimate", type="DECIMATE")
        mod.ratio = ratio
        apply_modifier_result(obj, mod)

    def recalculate_normals(self, object_id: str, *, inside: bool = False) -> None:
        import bmesh

        obj = get_object(object_id)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        if inside:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:], flip_multires=False)
        write_bmesh(bm, obj)

    def merge_by_distance(self, object_id: str, distance: float) -> RepairOutcome:
        import bmesh

        obj = get_object(object_id)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        before_verts = len(bm.verts)
        before_faces = len(bm.faces)
        # This bmesh build returns None from remove_doubles rather than the documented
        # dict(targetmap=...) — verified empirically — so count the weld from the vertex
        # delta instead of trusting the return value.
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=distance)
        fixed = before_verts - len(bm.verts)
        degenerate = max(0, before_faces - len(bm.faces))
        write_bmesh(bm, obj)
        return RepairOutcome(
            fixed=fixed,
            skipped=degenerate,
            reason=f"{degenerate} face(s) collapsed below 3 vertices" if degenerate else "",
        )

    def fill_holes(self, object_id: str, max_sides: int = 0) -> RepairOutcome:
        import bmesh

        obj = get_object(object_id)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()

        boundary: list[tuple[int, int]] = []
        for e in bm.edges:
            if e.is_boundary:
                a, b = e.verts[0].index, e.verts[1].index
                boundary.append((a, b) if a < b else (b, a))

        if not boundary:
            bm.free()
            return RepairOutcome()

        filled = skipped = 0
        for loop in boundary_loops(boundary):
            if max_sides and len(loop) > max_sides:
                skipped += 1
                continue
            try:
                bm.faces.new([bm.verts[i] for i in loop])
                filled += 1
            except ValueError:
                skipped += 1

        write_bmesh(bm, obj)
        return RepairOutcome(
            fixed=filled,
            skipped=skipped,
            reason=f"{skipped} hole(s) exceeded max_sides={max_sides}" if skipped else "",
        )
