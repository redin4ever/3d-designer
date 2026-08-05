"""``GAPS_SPECS`` — the MCP tool declarations for the corrective half of ``measure``.

Real ``ToolSpec`` values, not stubs: constructing them runs ``ToolSpec.__post_init__``
(``src/contracts/operations.py``) at import time — a mutating tool can never be handed to
the read-only INSPECT role (ADR-007) — whether or not ``src/mcp/`` has wired a handler up
yet. ``handler=None`` here is that placeholder, skipped at registration, the same
convention ``src/export/registry.py`` uses. Every repair in this package mutates the
engine, so every entry below is ``mutating=True`` and visible only to ``ToolRole.REFINE``
— never ``INSPECT``, whose entire concurrency guarantee (ADR-007) depends on none of its
tools being able to write.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["GAPS_SPECS"]

_OBJECT_ID = {"object_id": {"type": "string"}}

GAPS_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="fill_boundary_holes",
        description="Triangulate boundary loops (DefectClass.BOUNDARY_HOLE).",
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                **_OBJECT_ID,
                "max_sides": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Skip loops wider than this (0 = no limit).",
                },
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="weld_duplicates",
        description=(
            "Merge coincident vertices (DefectClass.LOOSE_OR_DUPLICATE, duplicate half)."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {**_OBJECT_ID, "tolerance": {"type": "number", "exclusiveMinimum": 0}},
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="remove_loose",
        description=(
            "Delete vertices referenced by no face (DefectClass.LOOSE_OR_DUPLICATE, "
            "loose half)."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {**_OBJECT_ID},
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="fix_normals",
        description=(
            "Reverse the winding of faces flagged as flipped relative to their "
            "neighbours (DefectClass.FLIPPED_NORMAL)."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {**_OBJECT_ID},
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="split_non_manifold",
        description=(
            "Report non-manifold edges/vertices (DefectClass.NON_MANIFOLD_EDGE, "
            "NON_MANIFOLD_VERTEX). Detection only — see CLAUDE.md for why this package "
            "cannot yet repair them."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {**_OBJECT_ID},
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="merge_shells",
        description="Weld vertices across an object's separate shells within max_distance.",
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                **_OBJECT_ID,
                "max_distance": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": ["object_id", "max_distance"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="close_visual_gap",
        description="Translate one part to touch another (DefectClass.VISUAL_GAP).",
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
                "max_gap": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": ["a", "b", "max_gap"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="repair",
        description=(
            "Run every applicable repair tier for one object, cheapest first, "
            "re-measuring between tiers so the result reflects what is actually left "
            "rather than what was attempted."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                **_OBJECT_ID,
                "classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Defect class names to restrict repair to; omit for all.",
                },
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
)
