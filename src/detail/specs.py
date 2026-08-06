"""``DETAIL_SPECS`` — the MCP tool declarations for the detail role (F-008).

Real ``ToolSpec`` values, not stubs: constructing them runs ``ToolSpec.__post_init__``
(``src/contracts/operations.py``) at import time, so a mutating tool handed to the read-only
INSPECT role, or a tool visible to no role at all, fails the moment this module is imported
rather than the first time somebody calls it. ``handler=None`` is the same placeholder
``ops.OP_SPECS`` and ``export.EXPORT_SPECS`` use — the composition root wires handlers;
registry *content* lives beside the operation, registry *policy* lives in ``src/mcp_server/``
(ADR-003).

**Why this file exists.** Verified in review: the ``DETAIL`` role had **zero** tools. Every
pass in this module was built, tested and correct, and nothing outside ``src/detail/``
imported any of it — ``mcp_server/registry.py::_load_optional`` collects a module's
``*_SPECS`` constant automatically and was getting ``()`` from here. The three passes were
named first-class at Gate A 8.4 and are a large part of why this product exists, since the
user's complaint (Gate A 1.3) was models that look like *"stitched together cubes"*.

**Every parameter carries a description naming its unit.** An agent acts on the schema
alone, and a review found one undescribed parameter cost a wasted round-trip because the
agent guessed a vector where a scalar was wanted. Numbers without units are the same failure
one step later: a bevel width of "2" is either a reasonable 2 mm or an object-destroying 2 m.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

__all__ = ["DETAIL_SPECS"]

_OBJECT_ID = {
    "type": "string",
    "description": "The mesh object to work on, by id. It must already exist.",
}

DETAIL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        # Named for the module function it exposes, which is also the name the composition
        # root already registers a handler under (`app/handlers.py`'s "detail" block). A tool
        # whose name does not match its handler is a tool an agent can see and nothing can
        # execute — discovered at call time, after the agent has committed to a plan.
        name="apply_edge_treatment",
        description=(
            "Bevel only the edges that would plausibly catch light, then clean up the "
            "triangulation the bevel leaves behind. A perfectly sharp CAD edge produces a "
            "hard, artificial specular break; even a tiny bevel produces the highlight line "
            "a viewer reads as real material. Bevelling *every* edge is itself an "
            "artificiality tell (Gate A 8.3), so this selects a proper subset: edges that "
            "fold by at least min_dihedral_deg, are convex, and are not facing away from "
            "world up. The response states which edges it chose and why — e.g. '8 of 18 "
            "edges, because they are convex and exposed' — so a call that selected too few "
            "can be re-run with a lower min_dihedral_deg rather than guessed at. Refuses, "
            "naming the rule, on an object with unapplied non-uniform scale: bevel width is "
            "computed in object space and an unapplied scale silently produces an uneven "
            "bevel."
        ),
        roles=(ToolRole.DETAIL,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": _OBJECT_ID,
                "segments": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 2,
                    "description": (
                        "How many faces across the bevel: 1 is a flat chamfer, 2 reads as "
                        "rounded at normal viewing distance. Each extra segment adds "
                        "triangles along every bevelled edge and makes each strip narrower, "
                        "so raising it costs budget and worsens triangle aspect ratio. "
                        "Count, not a length."
                    ),
                },
                "min_dihedral_deg": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 180,
                    "default": 30.0,
                    "description": (
                        "Degrees. The smallest fold between two faces that still counts as "
                        "an edge worth bevelling. 0 degrees is perfectly flat (nothing to "
                        "bevel); 90 is a box corner. Lower this to catch shallower creases."
                    ),
                },
                "convex_only": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true, skip re-entrant creases (the inside corner of an open "
                        "box). They are exactly as sharp as an outward corner but never "
                        "catch a highlight the way one does."
                    ),
                },
                "exclude_hidden": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true, skip edges whose faces point predominantly away from "
                        "world up — the underside of an object resting on a surface. This "
                        "is what stops a plain box selecting all twelve of its edges."
                    ),
                },
                "width_fraction": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "default": 0.004,
                    "description": (
                        "Bevel width as a fraction of the object's longest axis, so a "
                        "doorknob and a warehouse wall get proportionate bevels rather than "
                        "the same absolute one. 0.004 is 4 mm on a 1 m object."
                    ),
                },
                "min_width": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "default": 0.0005,
                    "description": (
                        "Metres. Lower clamp on the computed width — below about half a "
                        "millimetre a bevel is imperceptible and pure added triangle cost."
                    ),
                },
                "max_width": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "default": 0.01,
                    "description": (
                        "Metres. Upper clamp on the computed width — a warehouse-scale "
                        "object would otherwise get a bevel that reads as a modelling error."
                    ),
                },
                "cleanup": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Re-triangulate the flat faces after bevelling. On by default: a raw "
                        "bevel leaves them ear-clipped into needle triangles (measured at "
                        "1378:1 on a stair tread) which shade, bake and subdivide badly. Set "
                        "false only to measure the bevel in isolation."
                    ),
                },
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=(
            "soften the edges on the stair treads so they catch light",
            "bevel the porch post, and tell me which edges it picked and why",
        ),
    ),
    ToolSpec(
        name="add_panel_lines",
        description=(
            "Cut evenly spaced grooves across an object — the seams that read as separate "
            "manufactured panels rather than one extruded block. Adds geometry (it cuts, it "
            "does not just mark an attribute). Reports changed=false, rather than claiming "
            "success, when the object is too small along the chosen axis for even one groove "
            "at this spacing."
        ),
        roles=(ToolRole.DETAIL,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": _OBJECT_ID,
                "spacing": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": (
                        "Metres between one groove and the next, measured along `axis`. "
                        "0.6 puts a seam every 600 mm."
                    ),
                },
                "depth": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": (
                        "Metres each groove cuts into the surface. A few millimetres reads "
                        "as a panel seam; deeper reads as a slot."
                    ),
                },
                "axis": {
                    "type": "string",
                    "enum": ["x", "y", "z"],
                    "default": "z",
                    "description": (
                        "The world axis the grooves are spaced along — panel lines on a wall "
                        "run differently from panel lines on a hull plate, and this tool does "
                        "not guess which you meant."
                    ),
                },
            },
            "required": ["object_id", "spacing", "depth"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=(
            "cut panel lines every 60 cm across the hull plate",
            "add shallow seams up the wall so it does not read as one poured slab",
        ),
    ),
    ToolSpec(
        name="add_greebles",
        description=(
            "Scatter small relief detail across an object's upward-facing surface. "
            "Deliberately not uniform: greebling everything reads as noise rather than "
            "detail, so a contiguous fraction of the surface is reserved calm. Reproducible "
            "— the same object, density, rest_fraction and seed always produce the same "
            "geometry, so the pass can be reviewed, replayed and undone."
        ),
        roles=(ToolRole.DETAIL,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": _OBJECT_ID,
                "density": {
                    "type": "number",
                    "minimum": 0,
                    "description": (
                        "Roughly how many greebles are attempted per square metre of "
                        "footprint. Higher values crowd the surface; 0 scatters nothing."
                    ),
                },
                "rest_fraction": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.4,
                    "description": (
                        "Fraction of the surface deliberately left calm, as one contiguous "
                        "region rather than a speckle of skipped spots. 1.0 reserves "
                        "everything and is reported as a no-op, not as success."
                    ),
                },
                "seed": {
                    "type": "integer",
                    "default": 0,
                    "description": (
                        "Chooses the scatter. Same seed, same result; change it to get a "
                        "different arrangement of the same density. Not a count or a length."
                    ),
                },
            },
            "required": ["object_id", "density"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=(
            "scatter some mechanical clutter over the roof panel, keep half of it clean",
            "same greebles as before but with a different seed",
        ),
    ),
    ToolSpec(
        name="cleanup_bevel_topology",
        description=(
            "Re-triangulate an object's flat faces without moving a single vertex. Run "
            "automatically by apply_edge_treatment; exposed separately for a mesh bevelled "
            "elsewhere "
            "or treated with cleanup=false. A bevel leaves flat faces as n-gons which the "
            "engine ear-clips into needle triangles — on a stair tread that measures a mean "
            "aspect ratio of 109 with a worst triangle of 1378:1, and this brings it to 64 "
            "and 324:1, where 324:1 is the bevel strip itself and no triangulation can "
            "improve it. The silhouette, the vertex positions and watertightness are "
            "unchanged by construction. Declines, with the reason, on an object that has "
            "been UV unwrapped or carries more than one material slot."
        ),
        roles=(ToolRole.DETAIL,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": _OBJECT_ID,
                "coplanar_tolerance_deg": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 45,
                    "default": 0.5,
                    "description": (
                        "Degrees. How far two neighbouring faces may fold and still count as "
                        "one flat region. Must stay well below the fold of the bevel profile "
                        "itself (30 degrees per step on a two-segment 90-degree bevel) or a "
                        "region would swallow the bevel it is cleaning up."
                    ),
                },
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        mutating=True,
        examples=(
            "clean up the sliver triangles on the tread after that bevel",
            "the imported hull mesh shades badly along the flat panels — re-triangulate it",
        ),
    ),
)
