"""``EXPORT_SPECS`` — the MCP tool declarations for the export role.

Real ``ToolSpec`` values, not stubs: constructing them runs ``ToolSpec.__post_init__``
validation (``src/contracts/operations.py``) at import time, which is exactly what the
module task requires — contract validation must run whether or not the handlers behind
these tools are implemented yet. ``handler=None`` here is a placeholder ``src/mcp/`` skips
at registration, not an omission.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["EXPORT_SPECS"]

EXPORT_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="export_scene",
        description=(
            "Convert the named objects through a target engine profile (roblox, unity, "
            "unreal, godot) and write glTF/GLB. Always writes the file if the objects "
            "exist; any defect found (budget overage, non-manifold geometry, …) is reported "
            "in a warning banner and never blocks the write (Gate A 6.3)."
        ),
        roles=(ToolRole.EXPORT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Objects to export, by id.",
                },
                "path": {"type": "string", "description": "Output .glb/.gltf path."},
                "profile_name": {
                    "type": "string",
                    "default": "roblox",
                    "enum": ["roblox", "unity", "unreal", "godot"],
                },
                "asset_class": {
                    "type": "string",
                    "description": "Selects the per-class budget instead of the platform ceiling.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Acknowledge a BLOCKER-severity defect found before export.",
                },
            },
            "required": ["object_ids", "path"],
        },
        mutating=True,
        examples=("export the porch railing to roblox as out/porch.glb",),
    ),
    ToolSpec(
        name="check_export_budget",
        description=(
            "Check the named objects' triangle counts against a target profile's budget "
            "without exporting — the per-asset-class advisory budget when asset_class is "
            "given, otherwise the profile's hard per-mesh ceiling."
        ),
        roles=(ToolRole.EXPORT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "profile_name": {
                    "type": "string",
                    "default": "roblox",
                    "enum": ["roblox", "unity", "unreal", "godot"],
                },
                "asset_class": {"type": "string"},
            },
            "required": ["object_ids"],
        },
        mutating=False,
        examples=("check whether the hero prop is under the roblox budget",),
    ),
)
