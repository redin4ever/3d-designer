"""``acceptance_for``'s per-kind query construction.

Split out of ``validation.py`` purely to stay under the 300-line modularity cap — the
public name (``ops.acceptance_for``) is unaffected; see ``validation.py``, which re-exports
this module's one function.
"""

from __future__ import annotations

from typing import Any

from contracts import AcceptanceQuery, Comparison, DefectClass, MetricKind

__all__ = ["acceptance_for"]


def acceptance_for(kind: str, params: dict[str, Any]) -> tuple[AcceptanceQuery, ...]:
    """The re-runnable definition-of-done for one ``add_*``/``array_along`` call.

    Every kind in :data:`ops.OPS` returns at least one query. Where a meaningful scalar
    target is computable from ``params`` alone (a wall's volume, a staircase's total rise)
    the query compares against it; where the natural check is the absence of a defect
    class (an opening's cut, an array's coverage) it forbids that defect instead — both
    forms satisfy :class:`~contracts.AcceptanceQuery`'s own well-formedness check.
    """
    object_id = params.get("object_id", "")

    if kind == "add_primitive":
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_has_volume",
                description="the created primitive has positive volume",
                metric=MetricKind.VOLUME,
                subject=object_id,
                expected=1e-9,
                comparison=Comparison.GTE,
            ),
        )

    if kind == "add_wall":
        length = (params["end"] - params["start"]).length()
        volume = length * params["thickness"] * params["height"]
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_volume",
                description="wall volume matches length x thickness x height",
                metric=MetricKind.VOLUME,
                subject=object_id,
                expected=volume,
                tolerance=max(1e-4, volume * 0.01),
                comparison=Comparison.EQ,
            ),
        )

    if kind == "add_floor":
        volume = params["width"] * params["depth"] * params["thickness"]
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_volume",
                description="floor slab volume matches width x depth x thickness",
                metric=MetricKind.VOLUME,
                subject=object_id,
                expected=volume,
                tolerance=max(1e-4, volume * 0.01),
                comparison=Comparison.EQ,
            ),
        )

    if kind == "add_opening":
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_clean_cut",
                description="the opening leaves no visual gap and no broken topology at the cut",
                forbidden_defects=(DefectClass.VISUAL_GAP, DefectClass.NON_MANIFOLD_EDGE),
                subject=params.get("wall_id", object_id),
            ),
        )

    if kind == "add_staircase":
        treads, rise = params["treads"], params["rise"]
        first_id = f"{object_id}_tread_000"
        last_id = f"{object_id}_tread_{treads - 1:03d}"
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_total_rise",
                description="the highest tread sits treads * rise above the lowest",
                metric=MetricKind.DISTANCE,
                subject=f"{first_id}|{last_id}",
                expected=treads * rise,
                tolerance=max(1e-4, rise * 0.05),
                comparison=Comparison.EQ,
            ),
        )

    if kind == "add_railing":
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_no_part_clipping",
                description="posts, balusters and the top rail do not clip into one another",
                forbidden_defects=(DefectClass.PART_CLIPPING,),
                subject=object_id,
            ),
            AcceptanceQuery(
                query_id=f"{object_id}_no_visual_gap",
                description="the top rail meets every outer post with no visible gap",
                forbidden_defects=(DefectClass.VISUAL_GAP,),
                subject=object_id,
            ),
        )

    if kind == "array_along":
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_array_no_gap",
                description="arrayed instances leave no visual gap along the path",
                forbidden_defects=(DefectClass.VISUAL_GAP,),
                subject=object_id,
            ),
        )

    if kind == "add_lod_chain":
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_lod_within_budget",
                description="every LOD level stays within its triangle budget",
                forbidden_defects=(DefectClass.BUDGET_EXCEEDED,),
                subject=object_id,
            ),
        )

    # add_modular_kit
    return (
        AcceptanceQuery(
            query_id=f"{object_id}_grid_seams",
            description="kit pieces snap to the tiling grid with no visual gap at the seams",
            forbidden_defects=(DefectClass.VISUAL_GAP,),
            subject=object_id,
        ),
    )
