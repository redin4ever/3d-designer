"""``acceptance_for``'s per-kind query construction.

Split out of ``validation.py`` purely to stay under the 300-line modularity cap — the
public name (``ops.acceptance_for``) is unaffected; see ``validation.py``, which re-exports
this module's one function.
"""

from __future__ import annotations

from typing import Any

from contracts import AcceptanceQuery, Comparison, DefectClass, MetricKind, Vec3

__all__ = ["acceptance_for", "runtime_acceptance_for"]


def acceptance_for(
    kind: str, params: dict[str, Any], *, op_id: str = ""
) -> tuple[AcceptanceQuery, ...]:
    """The re-runnable definition-of-done for one ``add_*``/``array_along`` call.

    Every kind in :data:`ops.OPS` returns at least one query. Where a meaningful scalar
    target is computable from ``params`` alone (a wall's volume, a staircase's total rise)
    the query compares against it; where the natural check is the absence of a defect
    class (an opening's cut, an array's coverage) it forbids that defect instead — both
    forms satisfy :class:`~contracts.AcceptanceQuery`'s own well-formedness check.
    """
    object_id = params.get("object_id", "")
    output_prefix = op_id or object_id

    if kind == "add_impact_head":
        joints = [
            (f"{object_id}_body", f"{object_id}_top_plate", "top armor seats on body"),
            (f"{object_id}_body", f"{object_id}_cheek_front", "front cheek seats on body"),
            (f"{object_id}_body", f"{object_id}_cheek_back", "rear cheek seats on body"),
            (f"{object_id}_body", f"{object_id}_shoulder_left", "left shoulder sockets into body"),
            (f"{object_id}_body", f"{object_id}_shoulder_right", "right shoulder sockets into body"),
            (f"{object_id}_shoulder_left", f"{object_id}_collar_left", "left collar meets shoulder"),
            (f"{object_id}_shoulder_right", f"{object_id}_collar_right", "right collar meets shoulder"),
            (f"{object_id}_collar_left", f"{object_id}_face_left", "left face seats on collar"),
            (f"{object_id}_collar_right", f"{object_id}_face_right", "right face seats on collar"),
            (f"{object_id}_face_left", f"{object_id}_rim_left", "left retaining rim seats on face"),
            (f"{object_id}_face_right", f"{object_id}_rim_right", "right retaining rim seats on face"),
            (f"{object_id}_body", f"{object_id}_handle_socket", "handle socket enters body"),
        ]
        return tuple(
            AcceptanceQuery(
                query_id=f"{output_prefix}_impact_joint_{index}",
                description=description,
                metric=MetricKind.GAP_WIDTH,
                subject=f"{a}|{b}",
                expected=0.0,
                tolerance=1e-4,
                comparison=Comparison.EQ,
            )
            for index, (a, b, description) in enumerate(joints)
        )

    if kind == "add_roof_window":
        host = params.get("roof_id", "")
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_aligned", description="skylight follows the roof face",
                metric=MetricKind.SURFACE_ANGLE, subject=f"{host}|{object_id}_glass",
                expected=0.0, tolerance=1.0, comparison=Comparison.EQ,
            ),
            AcceptanceQuery(
                query_id=f"{output_prefix}_contact", description="skylight frame contacts the roof",
                metric=MetricKind.GAP_WIDTH, subject=f"{host}|{object_id}_frame",
                expected=0.0, tolerance=0.001, comparison=Comparison.EQ,
            ),
        )

    if kind == "add_wall_sign":
        host = params.get("wall_id", "")
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_aligned", description="sign follows the selected wall face",
                metric=MetricKind.SURFACE_ANGLE, subject=f"{host}|{object_id}",
                expected=0.0, tolerance=1.0, comparison=Comparison.EQ,
            ),
            AcceptanceQuery(
                query_id=f"{output_prefix}_contact", description="sign contacts the wall",
                metric=MetricKind.GAP_WIDTH, subject=f"{host}|{object_id}",
                expected=0.0, tolerance=0.001, comparison=Comparison.EQ,
            ),
        )

    if kind == "add_facade_ribs":
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_contact", description="façade ribs contact their wall",
                metric=MetricKind.GAP_WIDTH,
                subject=f"{params.get('wall_id', '')}|{object_id}", expected=0.0,
                tolerance=0.001, comparison=Comparison.EQ,
            ),
        )

    if kind == "add_gable_roof":
        joints = [
            (f"{object_id}_slope_neg", f"{object_id}_slope_pos", "sloped panels meet"),
            (f"{object_id}_ridge_cap", f"{object_id}_slope_neg", "ridge cap meets left panel"),
            (f"{object_id}_ridge_cap", f"{object_id}_slope_pos", "ridge cap meets right panel"),
            (
                f"{object_id}_ridge_cap", f"{object_id}_gable_neg_trim",
                "ridge cap meets front rake trim",
            ),
            (
                f"{object_id}_ridge_cap", f"{object_id}_gable_pos_trim",
                "ridge cap meets back rake trim",
            ),
        ]
        for gable in ("neg", "pos"):
            for eave in ("neg", "pos"):
                joints.append(
                    (
                        f"{object_id}_gable_{gable}_trim",
                        f"{object_id}_eave_{eave}_fascia",
                        "rake trim meets eave fascia across a compound miter",
                    )
                )
        return tuple(
            AcceptanceQuery(
                query_id=f"{output_prefix}_roof_joint_{index}",
                description=description,
                metric=MetricKind.GAP_WIDTH,
                subject=f"{a}|{b}",
                expected=0.0,
                tolerance=1e-4,
                comparison=Comparison.EQ,
            )
            for index, (a, b, description) in enumerate(joints)
        )

    if kind == "add_chimney":
        joints = [
            (f"{object_id}_flashing", f"{object_id}_shaft", "flashing closes around shaft"),
            (f"{object_id}_shaft", f"{object_id}_crown", "shaft supports crown"),
        ]
        for index in range(params["flue_count"]):
            flue = f"{object_id}_flue_{index:03d}"
            joints.extend(
                ((flue, f"{object_id}_crown", "flue meets crown"),
                 (f"{flue}_rim", flue, "flue rim meets flue body"))
            )
        return tuple(
            AcceptanceQuery(
                query_id=f"{output_prefix}_chimney_joint_{index}",
                description=description,
                metric=MetricKind.GAP_WIDTH,
                subject=f"{a}|{b}", expected=0.0, tolerance=1e-4,
                comparison=Comparison.EQ,
            )
            for index, (a, b, description) in enumerate(joints)
        )

    if kind == "add_staircase_to_landing":
        last_tread = f"{object_id}_tread_{params['treads'] - 1:03d}"
        landing_id = params["landing_id"]
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_meets_landing",
                description="the highest tread meets the named landing with no gap",
                metric=MetricKind.GAP_WIDTH,
                subject=f"{last_tread}|{landing_id}",
                expected=0.0,
                tolerance=1e-4,
                comparison=Comparison.EQ,
            ),
        )

    if kind in ("create_texture_material", "update_texture_material"):
        name = params.get("name", "material")
        return (
            AcceptanceQuery(
                query_id=f"{name}_material_recorded",
                description=f"managed texture material {name} remains addressable",
                metric=MetricKind.TRIANGLE_COUNT,
                subject=str(name), expected=0.0, comparison=Comparison.GTE,
            ),
        )

    if kind == "apply_texture_material":
        subject = next(iter(params.get("object_ids") or ()), "")
        return (
            AcceptanceQuery(
                query_id=f"{subject}_survived_texture_apply",
                description=f"{subject} still has positive volume after surfacing",
                metric=MetricKind.VOLUME,
                subject=subject, expected=1e-9, comparison=Comparison.GTE,
            ),
        )

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
        start = params["start"] if isinstance(params["start"], Vec3) else Vec3(*params["start"])
        end = params["end"] if isinstance(params["end"], Vec3) else Vec3(*params["end"])
        length = (end - start).length()
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
                description="the opened wall remains a positive, manifold solid",
                metric=MetricKind.VOLUME,
                subject=params.get("wall_id", object_id),
                expected=1e-9,
                comparison=Comparison.GTE,
                forbidden_defects=(DefectClass.BOUNDARY_HOLE, DefectClass.NON_MANIFOLD_EDGE),
            ),
        )

    if kind == "add_staircase":
        treads = params["treads"]
        last_id = f"{output_prefix}_tread_{treads - 1:03d}"
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_highest_tread_exists",
                description="the complete stair run includes a solid highest tread",
                metric=MetricKind.VOLUME,
                subject=last_id,
                expected=1e-9,
                comparison=Comparison.GTE,
            ),
        )

    if kind == "add_railing":
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_top_rail_exists",
                description="the railing includes one solid top rail",
                metric=MetricKind.VOLUME,
                subject=f"{output_prefix}_top_rail",
                expected=1e-9,
                comparison=Comparison.GTE,
                forbidden_defects=(
                    DefectClass.BOUNDARY_HOLE,
                    DefectClass.NON_MANIFOLD_EDGE,
                    DefectClass.SELF_INTERSECTION,
                ),
            ),
        )

    if kind == "array_along":
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_array_started",
                description="the array contains a solid first instance",
                metric=MetricKind.VOLUME,
                subject=f"{output_prefix}_i000",
                expected=1e-9,
                comparison=Comparison.GTE,
            ),
        )

    if kind == "add_lod_chain":
        return (
            AcceptanceQuery(
                query_id=f"{output_prefix}_lod_started",
                description="the LOD chain contains a solid level zero",
                metric=MetricKind.VOLUME,
                subject=f"{output_prefix}_lod00",
                expected=1e-9,
                comparison=Comparison.GTE,
            ),
        )

    # ---- the direct edits (Q-14) -------------------------------------------------------
    #
    # These move, resize or copy something that already exists rather than building
    # something new, so "did it work" is a different question and the query has to be
    # different too. The one thing every one of them must not do is destroy the object it
    # was pointed at — a scale that collapses a mesh to a plane, a rotate that produces a
    # degenerate transform, a duplicate that copies nothing. Positive volume is exactly that
    # check and it is re-measurable from live geometry, which is ADR-005's requirement.
    #
    # Deliberately NOT "no intersection": Q-21 chose to let an operator place something badly
    # and then be told what broke. Forbidding intersection here would turn every deliberate
    # overlap into an acceptance failure and make the tools fight the person using them.

    if kind in ("move_object", "rotate_object", "scale_object", "set_object_material"):
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_survived_edit",
                description=f"{object_id} still has positive volume after the edit",
                metric=MetricKind.VOLUME,
                subject=object_id,
                expected=1e-9,
                comparison=Comparison.GTE,
            ),
        )

    if kind in ("duplicate_object", "rename_object"):
        # The subject is the *new* object: the copy is what has to exist and be whole, and
        # asserting on the source would pass just as happily if the copy were never made.
        new_id = params.get("new_id") or f"{object_id}_copy"
        return (
            AcceptanceQuery(
                query_id=f"{new_id}_has_volume",
                description=f"{new_id} exists and carries the geometry it was copied from",
                metric=MetricKind.VOLUME,
                subject=new_id,
                expected=1e-9,
                comparison=Comparison.GTE,
            ),
        )

    if kind == "delete_object":
        # The only kind whose definition-of-done is about absence. Triangle count rather than
        # volume because a deleted object measures zero triangles and an evaluator can say so;
        # "volume of a thing that is not there" has no honest answer.
        return (
            AcceptanceQuery(
                query_id=f"{object_id}_is_gone",
                description=f"{object_id} contributes no geometry to the scene any more",
                metric=MetricKind.TRIANGLE_COUNT,
                subject=object_id,
                expected=0.0,
                comparison=Comparison.LTE,
            ),
        )

    # add_modular_kit
    return (
        AcceptanceQuery(
            query_id=f"{output_prefix}_kit_started",
            description="the modular kit contains a solid first grid piece",
            metric=MetricKind.VOLUME,
            subject=f"{output_prefix}_piece_00_00",
            expected=1e-9,
            comparison=Comparison.GTE,
        ),
    )


_RUNTIME_ACCEPTANCE_KINDS = frozenset({
    "add_primitive", "add_wall", "add_floor", "add_opening", "add_gable_roof", "add_chimney",
    "add_impact_head",
    "add_staircase", "add_staircase_to_landing", "add_railing", "array_along",
    "add_lod_chain", "add_modular_kit", "apply_texture_material", "move_object",
    "rotate_object", "scale_object", "set_object_material", "duplicate_object",
    "rename_object",
})


def runtime_acceptance_for(
    kind: str, params: dict[str, Any], *, op_id: str
) -> tuple[AcceptanceQuery, ...]:
    """Only queries the live geometry evaluator can honestly re-run after dispatch.

    Material creation and deletion currently lack an addressability/absence metric. Their
    legacy declaration queries remain available from :func:`acceptance_for`, but are not
    persisted as runtime gates that would crash on a non-mesh subject.
    """
    if kind not in _RUNTIME_ACCEPTANCE_KINDS:
        return ()
    return acceptance_for(kind, params, op_id=op_id)
