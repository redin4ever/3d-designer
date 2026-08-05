"""Static tool registry data for ``PhaseMixin.tools_for``.

Kept separate from ``phases.py`` (Rule 2: split along a distinct data shape) so the phase
machine's decision logic stays readable independent of how many tools exist. This is a
minimal, self-contained table — the real registry composition point (registry *content*
beside each operation module, registry *policy* in ``mcp``, per ``ARCHITECTURE.md``) is an
open implementation decision flagged in this task's ``contractRequests`` output (README.md
"Contract gaps", item 3). Every role gets between 1 and 8 tools; ``ToolRole.INSPECT``'s
entries are all ``mutating=False`` — ``ToolSpec.__post_init__`` would refuse to construct
the opposite combination, so this table cannot violate that guarantee even by accident.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["TOOLS_BY_ROLE"]

_EMPTY_SCHEMA: dict = {"type": "object", "properties": {}}


def _spec(name: str, description: str, role: ToolRole, *, mutating: bool) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        roles=(role,),
        input_schema=_EMPTY_SCHEMA,
        mutating=mutating,
    )


TOOLS_BY_ROLE: dict[ToolRole, tuple[ToolSpec, ...]] = {
    ToolRole.BLOCKOUT: (
        _spec("add_primitive", "Add a primitive (box/cylinder/sphere/...).", ToolRole.BLOCKOUT, mutating=True),
        _spec("duplicate_object", "Duplicate an existing object.", ToolRole.BLOCKOUT, mutating=True),
        _spec("delete_object", "Remove an object.", ToolRole.BLOCKOUT, mutating=True),
    ),
    ToolRole.REFINE: (
        _spec("align_face", "Align a face to another object's face.", ToolRole.REFINE, mutating=True),
        _spec("close_gap", "Close a visual gap between two parts.", ToolRole.REFINE, mutating=True),
        _spec("fix_normals", "Recalculate face winding.", ToolRole.REFINE, mutating=True),
    ),
    ToolRole.REPAIR: (
        _spec("fill_holes", "Triangulate boundary holes in a mesh.", ToolRole.REPAIR, mutating=True),
        _spec("weld_duplicates", "Weld coincident vertices.", ToolRole.REPAIR, mutating=True),
        _spec("repair", "Run the tiered repair pass, re-measuring between tiers.", ToolRole.REPAIR, mutating=True),
    ),
    ToolRole.ALIGN: (
        _spec("make_plumb", "Snap an object's local +Z to world up.", ToolRole.ALIGN, mutating=True),
        _spec("make_parallel", "Rotate an object parallel to another.", ToolRole.ALIGN, mutating=True),
        _spec("make_flush", "Remove the gap on one named axis.", ToolRole.ALIGN, mutating=True),
    ),
    ToolRole.DETAIL: (
        _spec("bevel_edges", "Bevel a selected edge set.", ToolRole.DETAIL, mutating=True),
        _spec("add_greeble", "Scatter small detail geometry.", ToolRole.DETAIL, mutating=True),
        _spec("vary_material", "Perturb a material's PBR values.", ToolRole.DETAIL, mutating=True),
    ),
    ToolRole.POLISH: (
        _spec("unwrap_uv", "Unwrap UVs for an object.", ToolRole.POLISH, mutating=True),
        _spec("bake_textures", "Bake texture channels.", ToolRole.POLISH, mutating=True),
        _spec("decimate_mesh", "Reduce triangle count toward budget.", ToolRole.POLISH, mutating=True),
    ),
    ToolRole.INSPECT: (
        _spec("measure_metrics", "Compute a metric query against live geometry.", ToolRole.INSPECT, mutating=False),
        _spec("list_defects", "Run defect detection over a scope.", ToolRole.INSPECT, mutating=False),
        _spec("propose_change", "Submit a proposal for the single writer to apply.", ToolRole.INSPECT, mutating=False),
    ),
    ToolRole.EXPORT: (
        _spec("export_gltf", "Export the model for a target platform profile.", ToolRole.EXPORT, mutating=False),
        _spec("export_report", "Preview export budget/defects without writing a file.", ToolRole.EXPORT, mutating=False),
    ),
    ToolRole.ADMIN: (
        _spec("checkpoint", "Name the current undo position.", ToolRole.ADMIN, mutating=True),
        _spec("rollback", "Undo to a named checkpoint.", ToolRole.ADMIN, mutating=True),
        _spec("execute_raw", "Run arbitrary code against the engine (ADR-009).", ToolRole.ADMIN, mutating=True),
    ),
}
