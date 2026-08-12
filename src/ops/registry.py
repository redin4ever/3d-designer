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
from .chimney import add_chimney
from .primitives import add_primitive
from .railing import add_railing
from .roof import add_gable_roof
from .landing_stairs import add_staircase_to_landing
from .stairs import add_staircase
from .transform import (
    delete_object,
    duplicate_object,
    move_object,
    rename_object,
    rotate_object,
    scale_object,
    set_object_material,
)
from .texture_materials import (
    TEXTURE_MATERIAL_SPECS,
    apply_texture_material,
    create_texture_material,
    update_texture_material,
)

__all__ = ["OPS", "OP_SPECS", "EDIT_SPECS"]

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
    "add_gable_roof": add_gable_roof,
    "add_chimney": add_chimney,
    "add_opening": add_opening,
    "add_staircase": add_staircase,
    "add_staircase_to_landing": add_staircase_to_landing,
    "add_railing": add_railing,
    "array_along": array_along,
    "add_lod_chain": add_lod_chain,
    "add_modular_kit": add_modular_kit,
    # The direct edits (Q-14). Registered here with everything else, deliberately: Q-19 chose
    # one shared history, and OPS is what `scene` replays through. An operator's nudge and an
    # agent's staircase are the same kind of thing to everything downstream of this dict.
    "move_object": move_object,
    "rotate_object": rotate_object,
    "scale_object": scale_object,
    "delete_object": delete_object,
    "duplicate_object": duplicate_object,
    "rename_object": rename_object,
    "set_object_material": set_object_material,
    "create_texture_material": create_texture_material,
    "update_texture_material": update_texture_material,
    "apply_texture_material": apply_texture_material,
}



#: The direct edits (Q-14). BLOCKOUT and REFINE both, because moving a part four centimetres
#: is as much a polish action as a roughing-out one — and because the operator reaching for
#: these should not depend on which phase the run happens to be in.
_EDIT_ROLES = (ToolRole.BLOCKOUT, ToolRole.REFINE)

_SNAP_SCHEMA = {
    "type": "number",
    "minimum": 0,
    "description": "Grid to snap to, in metres. 0 disables snapping. Defaults to 0.1.",
}

EDIT_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="move_object",
        description=(
            "Put one existing object at a world position. Snaps to a 0.1 m grid unless "
            "snap=0. The smallest correction there is: use it instead of rebuilding "
            "something that is only in the wrong place."
        ),
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "translation": _VEC3_SCHEMA,
                "snap": _SNAP_SCHEMA,
            },
            "required": ["object_id", "translation"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="rotate_object",
        description=(
            "Turn one existing object about a world axis. Snaps to 15 degrees unless "
            "snap_degrees=0."
        ),
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "axis": {"type": "string", "enum": ["x", "y", "z"]},
                "degrees": {"type": "number"},
                "snap_degrees": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Angle to snap to, in degrees. 0 disables. Defaults to 15.",
                },
            },
            "required": ["object_id", "axis", "degrees"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="scale_object",
        description="Resize one existing object. Every component must be non-zero.",
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {"object_id": {"type": "string"}, "scale": _VEC3_SCHEMA},
            "required": ["object_id", "scale"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="delete_object",
        description="Remove one object from the scene.",
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {"object_id": {"type": "string"}},
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="duplicate_object",
        description=(
            "Copy one object. Pass an offset, or the copy sits exactly inside the original "
            "and looks like nothing happened."
        ),
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "new_id": {"type": "string"},
                "offset": _VEC3_SCHEMA,
                "snap": _SNAP_SCHEMA,
            },
            "required": ["object_id", "new_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="rename_object",
        description=(
            "Give one object a different id. Refused if the new name is taken — the engine "
            "uniquifies on collision, so it would otherwise silently produce a third name."
        ),
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {"object_id": {"type": "string"}, "new_id": {"type": "string"}},
            "required": ["object_id", "new_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="set_object_material",
        description="Point one of an object's material slots at an existing material.",
        roles=_EDIT_ROLES,
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "material_id": {"type": "string"},
                "slot": {"type": "integer", "minimum": 0},
            },
            "required": ["object_id", "material_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
)

OP_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="add_primitive",
        description=(
            "Place one named, validated primitive mesh (cube, cylinder, sphere, plane, "
            "cone, torus). Not the default tool — use a semantic construction operation "
            "when one describes the intended object; those operations are themselves "
            "built from primitives and preserve architectural relationships (ADR-004)."
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
                # The handler has always accepted this and the schema has never declared
                # it, so no agent could place a primitive anywhere but the world origin —
                # every cube arrived at (0,0,0), half-buried in whatever floor was there,
                # and the only way out was an `align` tool in a later phase. A parameter a
                # handler supports and a schema hides is invisible: an agent acts on the
                # schema alone.
                "transform": {
                    "type": "object",
                    "description": (
                        "Where to place it. Omit to place at the world origin, which will "
                        "usually intersect anything already there."
                    ),
                    "properties": {
                        "translation": _VEC3_SCHEMA,
                        "rotation": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                            "description": "Quaternion [w, x, y, z].",
                        },
                        "scale": _VEC3_SCHEMA,
                    },
                    "additionalProperties": False,
                },
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
        name="add_gable_roof",
        description=(
            "Build a complete gable roof assembly from architectural dimensions: two "
            "sloped panels, ridge cap and full-face compound-mitered rake/eave corner trim. "
            "Use this for a house "
            "roof instead of approximating roof planes with a rotated cube. The origin "
            "is the footprint centre at the wall-top bearing plane."
        ),
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "origin": _VEC3_SCHEMA,
                "width": {"type": "number", "exclusiveMinimum": 0},
                "depth": {"type": "number", "exclusiveMinimum": 0},
                "pitch_degrees": {
                    "type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 80,
                },
                "thickness": {"type": "number", "exclusiveMinimum": 0},
                "overhang": {"type": "number", "minimum": 0},
                "trim_width": {"type": "number", "exclusiveMinimum": 0},
                "trim_depth": {"type": "number", "exclusiveMinimum": 0},
                "ridge_axis": {"type": "string", "enum": ["x", "y"]},
            },
            "required": [
                "object_id", "origin", "width", "depth", "pitch_degrees", "thickness",
                "overhang", "trim_width", "trim_depth", "ridge_axis",
            ],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="add_chimney",
        description=(
            "Build a complete masonry chimney from explicit architectural dimensions: "
            "shaft, tapered roof flashing, overhanging crown, and finished rimmed flues. "
            "Use this for a house chimney instead of a tall cube. Origin is the centre of "
            "the shaft footprint at its base."
        ),
        roles=(ToolRole.BLOCKOUT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "origin": _VEC3_SCHEMA,
                "width": {"type": "number", "exclusiveMinimum": 0},
                "depth": {"type": "number", "exclusiveMinimum": 0},
                "shaft_height": {"type": "number", "exclusiveMinimum": 0},
                "flashing_overhang": {"type": "number", "exclusiveMinimum": 0},
                "flashing_height": {"type": "number", "exclusiveMinimum": 0},
                "crown_overhang": {"type": "number", "exclusiveMinimum": 0},
                "crown_height": {"type": "number", "exclusiveMinimum": 0},
                "flue_count": {"type": "integer", "minimum": 1, "maximum": 4},
                "flue_radius": {"type": "number", "exclusiveMinimum": 0},
                "flue_height": {"type": "number", "exclusiveMinimum": 0},
                "rim_overhang": {"type": "number", "exclusiveMinimum": 0},
                "rim_height": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": [
                "object_id", "origin", "width", "depth", "shaft_height",
                "flashing_overhang", "flashing_height", "crown_overhang",
                "crown_height", "flue_count", "flue_radius", "flue_height",
                "rim_overhang", "rim_height",
            ],
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
        name="add_staircase_to_landing",
        description=(
            "Build supported entry stairs from a bottom start to an existing landing. "
            "The live landing bounds determine direction, run and rise, preventing the "
            "fixed-world-axis and guessed-height errors of a raw staircase. Produces thin "
            "treads and two side stringers; add a railing separately when needed."
        ),
        roles=(ToolRole.REFINE,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "landing_id": {"type": "string"},
                "start": _VEC3_SCHEMA,
                "treads": {"type": "integer", "exclusiveMinimum": 0},
                "width": {"type": "number", "exclusiveMinimum": 0},
                "tread_thickness": {"type": "number", "exclusiveMinimum": 0},
                "stringer_width": {"type": "number", "exclusiveMinimum": 0},
                "stringer_depth": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": [
                "object_id", "landing_id", "start", "treads", "width",
                "tread_thickness", "stringer_width", "stringer_depth",
            ],
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
) + EDIT_SPECS + TEXTURE_MATERIAL_SPECS
