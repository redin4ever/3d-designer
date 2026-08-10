"""MCP declaration for the model-file import operation.

The declaration stays beside the operation content. ``mcp_server.import_specs`` re-exports
this constant for the composition registry, while keeping ``handler=None`` so dispatch
routes the mutating call through the operation log and main wiring supplies the handler.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["IMPORT_SPECS"]

_IMPORT_ROLES = (
    ToolRole.BLOCKOUT,
    ToolRole.REFINE,
    ToolRole.DETAIL,
    ToolRole.POLISH,
)

IMPORT_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="import_model_file",
        description=(
            "Import one local GLB, glTF, FBX, OBJ, STL, PLY, or USD model into the current "
            "scene as one opaque, undoable operation. Imported meshes are normalized to "
            "internal metres and Z-up; ignored non-mesh content is returned as assumptions."
        ),
        roles=_IMPORT_ROLES,
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "format": "local-path",
                    "description": "Local filesystem path to the model; remote URLs are refused.",
                },
                "source_up": {
                    "type": "string",
                    "enum": ["AUTO", "X", "Y", "Z"],
                    "default": "AUTO",
                    "description": "Source up axis; AUTO lets the engine detect it.",
                },
                "unit_scale": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "default": 1.0,
                    "description": "Positive multiplier converting source units to metres.",
                },
                "flatten": {
                    "type": "boolean",
                    "default": True,
                    "description": "Flatten imported meshes into world transforms when true.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=None,
        mutating=True,
        examples=("import the local asset at assets/house.glb",),
    ),
)
