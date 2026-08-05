"""Stub — triangle-budget checks against a target profile. See ``src/export/README.md``.

Two thresholds exist per :class:`contracts.ExportProfile`: a hard, platform-imposed
``max_triangles_per_mesh`` (only Roblox declares one — a per-MeshPart ceiling that fails
import outright if crossed) and an advisory per-:class:`contracts.AssetClass` budget in
``profile.budgets``. :func:`check_budget` checks exactly one of the two per call — the
per-class budget when ``asset_class`` is given, the platform ceiling otherwise — per
ADR-010 and Gate A 12.2: budgets are tracked and warned against, never enforced by this tool
itself.

Nothing below is implemented yet — every function raises. Pure: read-only (only
``EngineProtocol.snapshot``).
"""

from __future__ import annotations

from typing import Sequence

from contracts import AssetClass, Defect, EngineProtocol, ExportProfile

__all__ = ["check_budget"]


def check_budget(
    engine: EngineProtocol,
    object_ids: Sequence[str],
    profile: ExportProfile,
    asset_class: AssetClass | None = None,
) -> tuple[Defect, ...]:
    """One :class:`contracts.Defect` of class ``BUDGET_EXCEEDED`` per object over its
    threshold, magnitude set to the overage (``triangle_count - threshold``); objects at or
    under the threshold contribute nothing.

    ``asset_class`` selects ``profile.budgets[asset_class]`` as the threshold *instead of*
    ``profile.max_triangles_per_mesh`` — never both, never a minimum of the two. If the
    selected threshold is ``None`` (no ceiling declared for this profile, or this class has
    none), no object checked against it can ever be flagged, however heavy its mesh is.
    """
    raise NotImplementedError("export.check_budget: not implemented")
