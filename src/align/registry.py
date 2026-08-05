"""``ALIGN_SPECS`` — the MCP tool declarations for this package's seven mutating
operations.

Real, fully-constructed data from the start, not a stub — mirrors ``ops/registry.py`` and
``constraints/anchors.py``'s ``AnchorResolution``: ``contracts.ToolSpec.__post_init__``
runs its own contract check (a mutating tool may never be handed to the read-only INSPECT
role, ADR-007) the moment this module is imported, so there is nothing behavioural here to
red/green against — only shape to get right up front. ``measure_angle`` is deliberately
absent: it is a pure query, not a tool this registry declares (there is no read-only role
in this package's scope to declare it under; a future ``inspect``-facing registry can add
it without touching this file).
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["ALIGN_SPECS"]

_AXIS_SCHEMA = {"type": "string", "enum": ["x", "y", "z"]}
_AUTO_AXIS_SCHEMA = {"type": "string", "enum": ["auto", "x", "y", "z"]}

ALIGN_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="make_parallel",
        description=(
            "Rotate an object by the minimal amount so its forward axis (or a named "
            "local axis) points exactly along a target object's same axis. One-shot: "
            "unlike a parallel_to constraint, this does not re-solve if the target "
            "moves afterwards."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "to": {"type": "string"},
                "axis": _AUTO_AXIS_SCHEMA,
            },
            "required": ["object_id", "to"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="make_perpendicular",
        description=(
            "Rotate an object so its forward axis (or a named local axis) lands at "
            "exactly 90 degrees from a target object's same axis."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "to": {"type": "string"},
                "axis": _AUTO_AXIS_SCHEMA,
            },
            "required": ["object_id", "to"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="make_coplanar",
        description=(
            "Rotate and move an object so every one of its own points lands in a "
            "target's face plane. Optionally names which of the target's planar faces "
            "by index; defaults to the target's own default face."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "to": {"type": "string"},
                "face": {"type": "integer", "minimum": 0},
            },
            "required": ["object_id", "to"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="make_plumb",
        description=(
            "Rotate an object so its local +Z equals world +Z — the single most "
            "consequential alignment in the product, the difference between a vertical "
            "railing post and one leaning at a stair's rake angle."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {"object_id": {"type": "string"}},
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="make_flush",
        description=(
            "Move an object along one named axis only, so its face on that axis shares "
            "a plane with a target's — no gap, no overlap. The other two position axes "
            "and all rotation are left untouched."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "to": {"type": "string"},
                "axis": _AXIS_SCHEMA,
            },
            "required": ["object_id", "to", "axis"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="snap_to_grid",
        description=(
            "Quantise an object's world bounds to regular multiples of a grid spacing, "
            "and optionally its yaw to the nearest multiple of a rotation step."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "grid": {"type": "number", "exclusiveMinimum": 0},
                "rotation_step_deg": {"type": "number", "minimum": 0},
            },
            "required": ["object_id", "grid"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
    ToolSpec(
        name="set_angle",
        description=(
            "Rotate an object's forward axis to exactly the requested angle in degrees "
            "from a target object's forward axis. 0 degrees is make_parallel; 90 is one "
            "of make_perpendicular's two valid results."
        ),
        roles=(ToolRole.ALIGN,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "to": {"type": "string"},
                "degrees": {"type": "number"},
            },
            "required": ["object_id", "to", "degrees"],
            "additionalProperties": False,
        },
        mutating=True,
    ),
)
