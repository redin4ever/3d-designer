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

from contracts import AssetClass, EngineProtocol, ExportReport

__all__ = ["export_scene", "banner_for"]


def export_scene(
    engine: EngineProtocol,
    object_ids: Sequence[str],
    path: str,
    *,
    profile_name: str = "roblox",
    asset_class: AssetClass | None = None,
    force: bool = False,
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
    raise NotImplementedError("export.export_scene: not implemented")


def banner_for(report: ExportReport) -> str:
    """Human-readable export summary.

    ``report.banner`` (``contracts.operations.ExportReport``) already renders defects and
    budget overage; this wraps it with one more line when ``report.forced`` is set, since
    that property has no way to mention ``forced`` itself and Gate A 6.3 requires an
    override never be silent.
    """
    raise NotImplementedError("export.banner_for: not implemented")
