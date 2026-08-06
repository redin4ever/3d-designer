"""Turning a failed acceptance query into a call an agent can actually make (ADR-012).

Its own file because it is its own decision — the mapping from "what is wrong" to "which of
the 29 real tools fixes it", with the real parameter names — and because getting it wrong is
now expensive. ADR-012 removed the promotion override at Gate B 1.1, so a refusal is the only
thing standing between an unattended agent and a phase it cannot leave. The user was told
that at the gate and chose the strictest option anyway; every failure naming its own fix is
the whole of the safety margin.

Every string produced here is a **call**, not advice: ``fill_boundary_holes(object_id='wall_n')``,
never "try filling the holes". The parameter names below are the ones the live registry
publishes, checked against ``mcp_server.build_registry()`` — a suggestion naming a tool that
does not exist, or an argument it does not take, sends the agent into the same retry loop as
saying nothing (the fictional tool table deleted at Gate B 4.4 did precisely that, for all 16
of its entries).
"""

from __future__ import annotations

import re

from contracts import AcceptanceQuery, Comparison, Defect, DefectClass, MetricKind

__all__ = ["for_defect", "for_query", "ADD_FIRST_OBJECT", "unwrap_call"]

#: What a single-object defect class is repaired by. These are genuinely different problems
#: with genuinely different repairs (``contracts.DefectClass``'s own docstrings are explicit
#: about it); collapsing them into one "fix the gaps" call is the most common mistake in this
#: domain, and would make the suggestion useless in most cases while looking helpful in all.
_SINGLE_OBJECT_FIX: dict[DefectClass, str] = {
    DefectClass.BOUNDARY_HOLE: "fill_boundary_holes(object_id={id!r})",
    DefectClass.NON_MANIFOLD_EDGE: "split_non_manifold(object_id={id!r})",
    DefectClass.NON_MANIFOLD_VERTEX: "split_non_manifold(object_id={id!r})",
    DefectClass.LOOSE_OR_DUPLICATE: "weld_duplicates(object_id={id!r})",
    DefectClass.FLIPPED_NORMAL: "fix_normals(object_id={id!r})",
    DefectClass.UNAPPLIED_TRANSFORM: "repair(object_id={id!r}, classes=['unapplied_transform'])",
    DefectClass.SELF_INTERSECTION: "repair(object_id={id!r}, classes=['self_intersection'])",
    DefectClass.BUDGET_EXCEEDED: "add_lod_chain(object_id={id!r}, ratios=[0.5, 0.25])",
}

_AXIS_IN_DETAIL = re.compile(r"along ([xyz])")
"""``measure.find_clipping`` states the insertion axis in its ``detail`` string and nowhere
else — :class:`contracts.Defect` carries no structured axis field. Reading it back out is a
parse, and parses rot; it is contained to this one line, defaults safely, and a contract
request for a structured ``axis`` on ``Defect`` is filed alongside this pass."""

ADD_FIRST_OBJECT = "add_primitive(object_id='block_00', kind='cube', size=[1.0, 1.0, 1.0])"
"""The fix for "this phase has produced no geometry at all"."""


def unwrap_call(object_id: str) -> str:
    return f"unwrap_uvs(object_id={object_id!r})"


def for_defect(defect: Defect) -> str:
    """The concrete call that repairs ``defect``, or ``""`` if this module knows of none."""
    if defect.defect_class is DefectClass.PART_CLIPPING:
        match = _AXIS_IN_DETAIL.search(defect.detail)
        axis = match.group(1) if match else "x"
        return (
            f"make_flush(object_id={defect.object_id!r}, "
            f"to={defect.other_object_id!r}, axis={axis!r})"
        )
    if defect.defect_class is DefectClass.VISUAL_GAP:
        gap = defect.magnitude if defect.magnitude is not None else 0.01
        return (
            f"close_visual_gap(a={defect.object_id!r}, b={defect.other_object_id!r}, "
            f"max_gap={max(gap * 2, 0.01):.4g})"
        )
    template = _SINGLE_OBJECT_FIX.get(defect.defect_class)
    return template.format(id=defect.object_id) if template else ""


def for_query(query: AcceptanceQuery, defects: tuple[Defect, ...]) -> str:
    """The call that would make ``query`` pass.

    Prefers the defect that actually failed it — the defect knows which object is broken and,
    for a pairwise class, which pair — and falls back to the query's own declared shape when
    a comparison failed with no defect to point at (an over-budget triangle count, say).
    """
    for defect in defects:
        call = for_defect(defect)
        if call:
            return call

    if query.comparison is not Comparison.NONE and query.metric is MetricKind.TRIANGLE_COUNT:
        return f"add_lod_chain(object_id={query.subject!r}, ratios=[0.5, 0.25])"
    for defect_class in query.forbidden_defects:
        template = _SINGLE_OBJECT_FIX.get(defect_class)
        if template:
            return template.format(id=query.subject)
    return ""
