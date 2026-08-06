"""``MEASURE_SPECS`` — the tool declarations that make this module reachable.

Everything in ``measure`` was implemented, tested and green, and this constant did not
exist: ``mcp_server.registry._load_optional("measure", "MEASURE_SPECS")`` collected ``()``,
so no connected agent could ask for a distance, a gap, an angle, a clipping check or a
defect report. The product's headline claim is tool-computed spatial truth in place of a
model eyeballing a render — and the tools were not callable.

**Six, not sixteen.** ADR-003 puts the accuracy-optimal visible set at about 5-8 per role,
and past that agents invent tool names and borrow argument schemas from the wrong tool.
This role also gains session tools from elsewhere, so the seven single-object metrics are
grouped into one ``measure_dimensions`` rather than published one apiece, and the ten defect
classes are grouped into one ``defect_report``.

**Every parameter carries its unit in its own description.** A review found
``add_opening.position`` with no description; an agent read the name, guessed ``[x, y, z]``
for a scalar, and wasted a round-trip. A schema is what an agent acts on without reading
source.

Registry *content* lives beside the operation it declares (this file); registry *policy* —
transports, role partitioning, capping — is ``src/mcp_server/``'s and is not decided here.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

from . import _handlers as h

__all__ = ["MEASURE_SPECS", "bind_engine"]

bind_engine = h.bind_engine

_OBJECT_IDS_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "description": (
        "Object ids, exactly as the operation that created them reported. Ids are "
        "predictable: a railing's posts are '<op_id>_post_000' upward in path order."
    ),
}

_JOINERY_SCHEMA = {
    "type": "array",
    "description": (
        "Intersections that are meant to be there. No geometry test can tell a post "
        "socketed 500mm into a deck from two posts wrongly overlapping — both are the same "
        "overlap. Declare the intended joints here and only the rest are reported; without "
        "this a staircase and its railing report dozens of defects that are all correct."
    ),
    "items": {
        "type": "object",
        "properties": {
            "object_id": {
                "type": "string",
                "description": "The part that goes in — the post, the tenon, the peg.",
            },
            "into_object_id": {
                "type": "string",
                "description": "The part it goes into — the deck, the mortise, the stringer.",
            },
            "depth": {
                "type": "number",
                "exclusiveMinimum": 0,
                "description": (
                    "How far in it is meant to go, in metres, measured along `axis`. An "
                    "overlap deeper than this is still reported."
                ),
            },
            "axis": {
                "type": "string",
                "enum": ["x", "y", "z"],
                "description": (
                    "World axis the part is inserted along. Leave it out only when the "
                    "joint is unambiguous: the smallest overlap of a post driven through a "
                    "deck is the post's own cross-section, which stays tiny however far "
                    "through it goes, so a depth without an axis can permit a post clean "
                    "through."
                ),
            },
            "tolerance": {
                "type": "number",
                "minimum": 0,
                "description": "Slack around `depth`, in metres. Defaults to 0.001 (1mm).",
            },
            "reason": {
                "type": "string",
                "description": "Why this joint exists, for whoever reads the log later.",
            },
        },
        "required": ["object_id", "into_object_id", "depth"],
        "additionalProperties": False,
    },
}

_MARGIN_SCHEMA = {
    "type": "number",
    "minimum": 0,
    "description": (
        "How far apart, in metres, two objects may be and still be compared. 0 compares "
        "only objects whose bounding boxes already touch."
    ),
}

_A_SCHEMA = {"type": "string", "description": "First object id. Order does not affect the result."}
_B_SCHEMA = {"type": "string", "description": "Second object id. Order does not affect the result."}


def _pair_schema() -> dict:
    return {
        "type": "object",
        "properties": {"a": dict(_A_SCHEMA), "b": dict(_B_SCHEMA)},
        "required": ["a", "b"],
        "additionalProperties": False,
    }


MEASURE_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="measure_distance",
        description=(
            "Closest surface-to-surface distance between two objects, in metres. Measured "
            "against real triangles, not bounding boxes, so a rotated beam reads correctly; "
            "0 when they touch or overlap, never a negative penetration depth — use "
            "find_clipping for that. Ask for this instead of judging it from a render: "
            "visual distance estimates land within 2x of truth about 37% of the time."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema=_pair_schema(),
        handler=h.measure_distance,
        mutating=False,
        examples=("how far is the railing from the wall",),
    ),
    ToolSpec(
        name="measure_gap",
        description=(
            "Shortest empty span between two objects, in metres — the number a 'close every "
            "gap under 5mm' task is defined against. 0 when the two touch or overlap."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema=_pair_schema(),
        handler=h.measure_gap,
        mutating=False,
        examples=("is the tread actually meeting the stringer",),
    ),
    ToolSpec(
        name="measure_angle",
        description=(
            "Angle in degrees between two objects' long axes, 0 to 180. A post tipped two "
            "degrees off plumb produces no visual tell in a render; this is the number that "
            "catches it."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema=_pair_schema(),
        handler=h.measure_angle,
        mutating=False,
        examples=("are these two balusters parallel",),
    ),
    ToolSpec(
        name="measure_dimensions",
        description=(
            "Size, world bounding box, enclosed volume and triangle count for each named "
            "object, in one call. Volume is the true enclosed volume, not the box multiplied "
            "out, so it is right for anything that is not a box. Triangle count is what "
            "export budgets are checked against."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema={
            "type": "object",
            "properties": {"object_ids": dict(_OBJECT_IDS_SCHEMA)},
            "required": ["object_ids"],
            "additionalProperties": False,
        },
        handler=h.measure_dimensions,
        mutating=False,
        examples=("how big is the staircase and how heavy is it to export",),
    ),
    ToolSpec(
        name="find_clipping",
        description=(
            "Parts interpenetrating where they should not. Checks the named objects against "
            "each other and against everything they are near, and reports how deep each "
            "overlap is and how far something must move to clear it. Declare intended "
            "joints in `joinery` — this is the one defect no geometry test can classify "
            "alone, because a correct socket and a collision are the same overlap."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_ids": dict(_OBJECT_IDS_SCHEMA),
                "joinery": dict(_JOINERY_SCHEMA),
                "margin": dict(_MARGIN_SCHEMA),
            },
            "required": ["object_ids"],
            "additionalProperties": False,
        },
        handler=h.find_clipping,
        mutating=False,
        examples=(
            "does the new railing clip the treads, given its posts are meant to be 60mm "
            "into each tread",
        ),
    ),
    ToolSpec(
        name="defect_report",
        description=(
            "Everything wrong with the named objects and their surroundings, in one call: "
            "holes, non-manifold edges and vertices, loose and duplicate geometry, flipped "
            "normals, self-intersections, unapplied scale, clipping against neighbours, and "
            "joints that should meet and do not. Each defect names its class, its severity, "
            "how big it is and what to do about it. The report states the scope it actually "
            "examined, so a clean result is never mistaken for a clean whole scene."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_ids": dict(_OBJECT_IDS_SCHEMA),
                "include_neighbours": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Also compare each object with the objects around it. Off gives the "
                        "single-object checks only, which is faster and cannot see clipping "
                        "or an open joint."
                    ),
                },
                "joinery": dict(_JOINERY_SCHEMA),
                "max_gap": {
                    "type": "number",
                    "minimum": 0,
                    "default": 0.005,
                    "description": (
                        "Widest empty span, in metres, still counted as a joint that should "
                        "have met. 0 skips the check."
                    ),
                },
            },
            "required": ["object_ids"],
            "additionalProperties": False,
        },
        handler=h.defect_report,
        mutating=False,
        examples=("is the staircase ready to export",),
    ),
)
