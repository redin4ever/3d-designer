"""``OPS`` and ``OP_SPECS`` — the construction library's registry.

``OPS`` is what ``scene`` replays every logged operation through: ``OPS[op.kind](engine,
op)``. ``OP_SPECS`` is what ``mcp`` turns into tool declarations for the BLOCKOUT and REFINE
roles. Both are real, constructed values, never stubs — ``contracts.ToolSpec.__post_init__``
runs its own contract check, a mutating tool may never be handed to the read-only INSPECT
role (ADR-007), at construction time, and that check must run, and pass, the moment this
module is imported. Getting it wrong here would mean the construction library — the module
ADR-004 calls "the main ongoing product work" — is also the one that breaks the concurrency
guarantee every INSPECT sub-agent depends on.

Registry *content* (this file) lives beside the operations it declares; registry *policy*
(transports, role-partitioning into 5-8 visible tools, image downscaling) lives in
``src/mcp/`` (ADR-003) and is out of scope here.

Role assignment: BLOCKOUT for the operations that rough out massing (a primitive, a wall, a
floor, a repeated instance, a tiled kit); REFINE for the operations that depend on
something else already existing and demand tighter tolerance (an opening cut into a
standing wall, a staircase's tread-to-tread rise, the flagship railing, a LOD chain
simplifying an already-finished hero mesh).
"""

from __future__ import annotations

from contracts import HandlerRegistry, ToolRole, ToolSpec

from .architecture import add_floor, add_opening, add_wall
from .arrays import add_lod_chain, add_modular_kit, array_along
from .primitives import add_primitive
from .railing import add_railing
from .stairs import add_staircase

__all__ = ["OPS", "OP_SPECS"]

_VEC3_SCHEMA = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
    "description": "[x, y, z] in metres.",
}

_PATH_SCHEMA = {
    "type": "array",
    "items": _VEC3_SCHEMA,
    "minItems": 2,
    "description": (
        "Polyline vertices, in order. A vertex where the direction changes is a corner."
    ),
}

_PAIR_SCHEMA = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}


OPS: HandlerRegistry = {
    "add_primitive": add_primitive,
    "add_wall": add_wall,
    "add_floor": add_floor,
    "add_opening": add_opening,
    "add_staircase": add_staircase,
    "add_railing": add_railing,
    "array_along": array_along,
    "add_lod_chain": add_lod_chain,
    "add_modular_kit": add_modular_kit,
}


OP_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="add_primitive",
        description=(
            "Place one named, validated primitive mesh (cube, cylinder, sphere, plane, "
            "cone, torus). Not the default tool — the other eight operations in this "
            "library are themselves built from primitives; reach for one of those first "
            "(ADR-004)."
        ),
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["cube", "cylinder", "sphere", "plane", "cone", "torus"],
                },
                "size": _VEC3_SCHEMA,
            },
            "required": ["object_id", "kind", "size"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_wall",
        description="A straight wall of given length (start to end), height and thickness.",
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "start": _VEC3_SCHEMA,
                "end": _VEC3_SCHEMA,
                "height": {"type": "number", "exclusiveMinimum": 0},
                "thickness": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": ["object_id", "start", "end", "height", "thickness"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_floor",
        description="A rectangular floor slab of given width, depth and thickness.",
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "width": {"type": "number", "exclusiveMinimum": 0},
                "depth": {"type": "number", "exclusiveMinimum": 0},
                "thickness": {"type": "number", "exclusiveMinimum": 0},
                "origin": _VEC3_SCHEMA,
            },
            "required": ["object_id", "width", "depth", "thickness"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_opening",
        description=(
            "Boolean a door or window opening out of an existing wall. Fails with a named "
            "ToolError, never a silent no-op, when the opening does not actually "
            "intersect the wall."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "wall_id": {"type": "string"},
                "position": {"type": "number", "minimum": 0},
                "width": {"type": "number", "exclusiveMinimum": 0},
                "height": {"type": "number", "exclusiveMinimum": 0},
                "sill_height": {"type": "number", "minimum": 0},
            },
            "required": ["object_id", "wall_id", "position", "width", "height"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_staircase",
        description="A straight run of treads at a given rise, run and width.",
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "treads": {"type": "integer", "exclusiveMinimum": 0},
                "rise": {"type": "number", "exclusiveMinimum": 0},
                "run": {"type": "number", "exclusiveMinimum": 0},
                "width": {"type": "number", "exclusiveMinimum": 0},
                "origin": _VEC3_SCHEMA,
            },
            "required": ["object_id", "treads", "rise", "run", "width"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_railing",
        description=(
            "A railing along a path: posts plumb in world +Z regardless of slope, forced "
            "at every corner in addition to the regular pitch; a top rail terminating at "
            "post centrelines; balusters plumb through slope changes, spaced to the "
            "requested clear opening (not centre-to-centre pitch). The flagship operation "
            "this library exists for (ADR-004)."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "path": _PATH_SCHEMA,
                "height": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "Top rail height above the walking surface.",
                },
                "post_spacing": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": (
                        "Nominal pitch between posts, along the path's arc length. "
                        "Corners get an extra post regardless."
                    ),
                },
                "baluster_gap": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": (
                        "Required CLEAR opening between adjacent balusters — not "
                        "centre-to-centre pitch."
                    ),
                },
                "post_size": _PAIR_SCHEMA,
                "baluster_size": _PAIR_SCHEMA,
                "rail_size": _PAIR_SCHEMA,
            },
            "required": ["object_id", "path", "height", "post_spacing", "baluster_gap"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=(
            "A guard rail along a stair's outer stringer, 0.9m high, posts every 1.2m, "
            "100mm clear baluster gap.",
        ),
    ),
    ToolSpec(
        name="array_along",
        description="Instance one object along a path at a regular spacing, corners resampled.",
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "path": _PATH_SCHEMA,
                "spacing": {"type": "number", "exclusiveMinimum": 0},
                "keep_upright": {"type": "boolean"},
            },
            "required": ["object_id", "path", "spacing"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_lod_chain",
        description=(
            "Progressively simpler copies of an object at given simplification ratios; "
            "level 0 is unmodified."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "ratios": {
                    "type": "array",
                    "items": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                    "minItems": 1,
                },
            },
            "required": ["object_id", "ratios"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_modular_kit",
        description="Grid-aligned tiling pieces that seam without gaps.",
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "grid_size": {"type": "number", "exclusiveMinimum": 0},
                "piece_size": _VEC3_SCHEMA,
                "count_x": {"type": "integer", "exclusiveMinimum": 0},
                "count_y": {"type": "integer", "exclusiveMinimum": 0},
                "origin": _VEC3_SCHEMA,
            },
            "required": ["object_id", "grid_size", "piece_size", "count_x", "count_y"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
)
