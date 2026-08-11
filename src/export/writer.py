"""Stub — writes the converted scene through ``EngineProtocol.export_gltf`` and assembles
the :class:`contracts.ExportReport`. See ``src/export/README.md``.

Gate A 6.3, verbatim user decision: export is allowed with a warning banner, never blocked.
A scene with defects still produces a file and a report that names every one of them — this
is the one place ``ok`` does not mean "clean," it means "a file was written." Deliberately
independent of ``src/measure/`` (stubbed, and pulling it in here would take every export
call down with a ``NotImplementedError`` from a module this one does not need): whatever
structural pre-flight check backs the warning banner reads triangle/edge incidence directly
off ``EngineProtocol.snapshot()``, never through ``measure.find_non_manifold_edges``.

Nothing below is implemented yet — every function raises.
"""

from __future__ import annotations

from typing import Sequence

from contracts import (
    AssetClass,
    Defect,
    DefectClass,
    EngineProtocol,
    ExportReport,
    Severity,
    UpAxis,
    profile_for,
)

from .budget import check_budget

__all__ = ["export_scene", "banner_for"]


def _non_manifold_defects(engine: EngineProtocol, object_id: str) -> list[Defect]:
    """Structural pre-flight behind the warning banner. Reads triangle incidence straight
    off ``EngineProtocol.snapshot()`` — never through ``measure.find_non_manifold_edges``,
    which is stubbed and would take every export call down with it (see ``CLAUDE.md``).

    An edge with three or more incident triangles is :data:`DefectClass.NON_MANIFOLD_EDGE`
    (``contracts.measurement``); every other edge — shared by exactly two triangles, or
    bounding only one (an open boundary, a different defect class this module does not
    check) — is left alone.
    """
    snapshot = engine.snapshot(object_id)
    counts: dict[tuple[int, int], int] = {}
    for tri in snapshot.triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            counts[key] = counts.get(key, 0) + 1

    defects: list[Defect] = []
    for edge, incidence in counts.items():
        if incidence >= 3:
            defects.append(
                Defect.of(
                    DefectClass.NON_MANIFOLD_EDGE,
                    object_id,
                    f"edge {edge} has {incidence} incident faces",
                    magnitude=float(incidence),
                    unit="faces",
                )
            )
    return defects


def export_scene(
    engine: EngineProtocol,
    object_ids: Sequence[str],
    path: str,
    *,
    profile_name: str = "roblox",
    asset_class: AssetClass | None = None,
    force: bool = False,
    format_name: str | None = None,
) -> ExportReport:
    """Convert every object in ``object_ids`` through ``profile_name`` and write it via
    ``EngineProtocol.export_gltf``, passing every conversion field the profile carries —
    ``y_up=profile.up_axis is UpAxis.Y``, ``mirror_x=profile.flip_x``,
    ``negate_rotation=profile.negate_rotation``, ``scale=profile.to_target_units(1.0)``. An
    earlier draft of ``export_gltf`` exposed only ``y_up``, which left the two fields a
    left-handed target needs together unreachable — see
    ``contracts.engine.ExportOps.export_gltf``.

    Raises ``KeyError`` (via ``contracts.profile_for``) naming the profiles that do exist
    when ``profile_name`` is unknown.

    Structural defects (e.g. non-manifold edges) and :func:`export.check_budget` findings
    are collected and attached to the returned report — the single-mesh budget overage in
    ``ExportReport.budget``/``over_budget_by``, everything else in ``ExportReport.defects``
    — but neither ever prevents the write: ``ok`` is always ``True`` once the named objects
    exist and the engine call succeeds. ``force`` and the returned report's ``forced`` field
    exist only to make a knowing override of a BLOCKER-severity defect visible rather than
    silent (Gate A 6.3); they never change whether the file is written.
    """
    profile = profile_for(profile_name)

    structural_defects: list[Defect] = []
    for object_id in object_ids:
        structural_defects.extend(_non_manifold_defects(engine, object_id))
    has_blocker = any(d.severity is Severity.BLOCKER for d in structural_defects)

    budget_defects = check_budget(engine, object_ids, profile, asset_class)
    budget: int | None = None
    over_budget_by = 0
    if budget_defects:
        over_budget_by = int(max(d.magnitude for d in budget_defects))
        budget = (
            profile.budgets.get(asset_class) if asset_class is not None else profile.max_triangles_per_mesh
        )

    triangle_count = sum(engine.snapshot(object_id).triangle_count for object_id in object_ids)

    conversion = {
        "y_up": profile.up_axis is UpAxis.Y,
        "mirror_x": profile.flip_x,
        "negate_rotation": profile.negate_rotation,
        "scale": profile.to_target_units(1.0),
    }
    chosen_format = (format_name or "").lower().lstrip(".")
    if chosen_format and chosen_format not in {"glb", "gltf"}:
        engine.export_model(object_ids, path, **conversion)
    else:
        engine.export_gltf(object_ids, path, **conversion)

    return ExportReport(
        path=path,
        profile=profile.name,
        ok=True,
        triangle_count=triangle_count,
        defects=tuple(structural_defects),
        budget=budget,
        over_budget_by=over_budget_by,
        forced=force and has_blocker,
    )


def banner_for(report: ExportReport) -> str:
    """Human-readable export summary.

    ``report.banner`` (``contracts.operations.ExportReport``) already renders defects and
    budget overage; this wraps it with one more line when ``report.forced`` is set, since
    that property has no way to mention ``forced`` itself and Gate A 6.3 requires an
    override never be silent.
    """
    banner = report.banner
    if report.forced:
        banner += "\n  • export forced past a blocking defect"
    return banner
