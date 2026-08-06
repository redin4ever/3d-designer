"""``SESSION_SPECS`` — the four tools an agent needs to orient itself and finish
(Gate B 3.1).

``ToolRole.INSPECT`` had **zero** tools for the whole build. There was no way for a
connected agent to ask what phase it was in, what existed in the scene, or to advance a
phase, and Gate A 4.4 chose a fully autonomous run: against that registry, an autonomous
run can build forever and never promote, never export, never finish. These four close that.

They are declared here rather than beside an operation module because they are registry
*policy* — they report on the phase and on the registry itself, and no operation module
owns either. ``describe_object`` keeps exactly that name because
``contracts.ActionReport.detail_hint`` names it as a string that agents are told to call.

Three are ``INSPECT`` and ``mutating=False``, so many of them run concurrently with no
write lease (ADR-007). ``promote_phase`` is ``ADMIN``, which is legal in every phase
(``contracts.ALWAYS_LEGAL_ROLES``) — putting promotion behind a phase-scoped role would
make the phase an agent is stuck in the one thing preventing it from leaving.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec

from .phase_tools import get_phase, promote_phase
from .scene_query import DEFAULT_PAGE, MAX_PAGE, describe_object, list_objects

__all__ = ["SESSION_SPECS"]

_NO_PARAMS = {"type": "object", "properties": {}, "additionalProperties": False}

SESSION_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_phase",
        description=(
            "Where this session is and what it may do: the current phase, the roles legal "
            "in it, every tool callable right now, and each of the phase's acceptance "
            "queries with the ones that currently fail — each failure naming its subject, "
            "measured value, threshold and the operation that would fix it. Call this "
            "first in a new session, and after any refusal you did not expect."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema=dict(_NO_PARAMS),
        handler=get_phase,
        mutating=False,
        examples=("what phase am I in and what is stopping me leaving it",),
    ),
    ToolSpec(
        name="list_objects",
        description=(
            "The object ids in the scene with a compact summary of each (dimensions in "
            "metres, triangle count). Paged and filterable, never the whole scene: pass "
            f"prefix to narrow, limit (default {DEFAULT_PAGE}, max {MAX_PAGE}) and offset "
            "to page. The response says how many matched and where to continue."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema={
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "Only ids starting with this, e.g. 'rail_'. Empty means all.",
                },
                "limit": {
                    "type": "integer",
                    "default": DEFAULT_PAGE,
                    "description": f"How many to return, 1..{MAX_PAGE}. Larger values are clamped.",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Where to start; use next_offset from the previous call.",
                },
            },
            "additionalProperties": False,
        },
        handler=list_objects,
        mutating=False,
        examples=("what railings exist", "list the first 20 objects in the scene"),
    ),
    ToolSpec(
        name="describe_object",
        description=(
            "Everything measured about one object: dimensions in metres, world bounds, "
            "triangle/vertex/polygon counts, its transform, and every defect found on it. "
            "This is what an ActionReport's detail_hint points at when it summarises "
            "instead of listing per-object detail."
        ),
        roles=(ToolRole.INSPECT,),
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string", "description": "The object to describe."},
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        handler=describe_object,
        mutating=False,
        examples=("how big is stair_tread_004 and is anything wrong with it",),
    ),
    ToolSpec(
        name="promote_phase",
        description=(
            "Advance to the next phase — blockout -> refine -> detail -> polish — one step "
            "at a time. Succeeds only when every acceptance query of the current phase "
            "passes against live geometry; a refusal returns each failing query with its "
            "subject, measured value, threshold and the operation that would fix it. "
            "There is no override and no force parameter: fixing the failures is the only "
            "way forward (ADR-012)."
        ),
        roles=(ToolRole.ADMIN,),
        input_schema=dict(_NO_PARAMS),
        handler=promote_phase,
        mutating=True,
        examples=("blockout looks finished — move to refine",),
    ),
)
