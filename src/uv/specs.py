"""``UV_SPECS`` — the MCP tool declarations for the polish role.

Real ``ToolSpec`` values, not stubs — the same convention ``src/export/registry.py`` and
``src/ops/registry.py`` use: constructing them runs ``ToolSpec.__post_init__`` validation
(``src/contracts/operations.py``) at import time, so a mistake that hands a mutating tool to
``ToolRole.INSPECT`` fails at collection, not the first time some agent calls it.
``handler=None`` is a placeholder ``src/mcp/`` fills in at registration, not an omission.

Both tools mutate — one rewrites UV data, the other writes files to disk — so both are
``mutating=True`` and neither is visible to ``ToolRole.INSPECT``. The read-only
``uv_quality`` query deliberately has no entry here: a read-only tool belongs in an
INSPECT-role registry, and ``uv``'s only declared dependencies are ``contracts`` and
``measure`` (``.pipeline/modules.json``), not ``mcp`` — wiring ``uv_quality`` into a tool
registry is a decision for whichever module owns that registry, not this one.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["UV_SPECS"]

_SEAMS_SCHEMA = {
    "type": "array",
    "items": {"type": "integer", "minimum": 0},
    "description": (
        "Edge indices into MeshSnapshot.edges() to force as seams, overriding the "
        "automatic hard-crease suggestion. Omit to let the tool choose."
    ),
}

UV_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="unwrap_uvs",
        description=(
            "Full UV unwrap of one object. Agent-chosen seams override the automatic "
            "hard-crease suggestion when supplied."
        ),
        roles=(ToolRole.POLISH,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "seams": _SEAMS_SCHEMA,
                "method": {
                    "type": "string",
                    "default": "angle_based",
                    "enum": ["angle_based", "conformal"],
                },
                "margin": {"type": "number", "default": 0.001, "exclusiveMinimum": 0},
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=("unwrap the porch railing post with the default seam suggestion",),
    ),
    ToolSpec(
        name="bake_textures",
        description=(
            "Unwrap (if the object has no UVs yet) and bake albedo/normal/roughness texture "
            "maps for one object. Reports a missing windowed Blender context as a named, "
            "non-fatal limitation rather than failing obscurely or crashing."
        ),
        roles=(ToolRole.POLISH,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "seams": _SEAMS_SCHEMA,
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["albedo", "normal", "roughness"],
                },
                "resolution": {"type": "integer", "default": 1024, "exclusiveMinimum": 0},
                "output_dir": {"type": "string", "default": "."},
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=("bake 1k textures for the hero prop",),
    ),
)
