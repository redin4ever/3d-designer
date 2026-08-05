"""Stub ``ModifierOps`` — bevel, boolean, array-along-curve and the repair operations.

Every method raises. See ``src/engine/mesh.py`` for why: this file fixes the shape the
implementer inherits, with no logic of its own. ``array_along_curve`` with
``keep_upright=True`` is the single most behaviourally important method in the whole engine
— see ``ModifierOps.array_along_curve`` in ``src/contracts/engine.py`` and
``conformance.check_array_along_curve_keeps_instances_plumb_on_a_slope``.
"""

from __future__ import annotations

from typing import Sequence

from contracts import RepairOutcome, Vec3

__all__ = ["ModifierOpsMixin"]


class ModifierOpsMixin:
    """``ModifierOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def bevel_edges(
        self,
        object_id: str,
        width: float,
        segments: int = 2,
        edge_indices: Sequence[int] | None = None,
    ) -> None:
        raise NotImplementedError("engine.bevel_edges: not implemented")

    def boolean(self, target_id: str, cutter_id: str, mode: str, solver: str = "exact") -> None:
        raise NotImplementedError("engine.boolean: not implemented")

    def solidify(self, object_id: str, thickness: float) -> None:
        raise NotImplementedError("engine.solidify: not implemented")

    def array_along_curve(
        self,
        object_id: str,
        curve_points: Sequence[Vec3],
        spacing: float,
        *,
        keep_upright: bool,
        extra_points: Sequence[Vec3] = (),
        name_template: str = "{base}_i{index:03d}",
    ) -> list[str]:
        raise NotImplementedError("engine.array_along_curve: not implemented")

    def decimate(self, object_id: str, ratio: float) -> None:
        raise NotImplementedError("engine.decimate: not implemented")

    def recalculate_normals(self, object_id: str, *, inside: bool = False) -> None:
        raise NotImplementedError("engine.recalculate_normals: not implemented")

    def merge_by_distance(self, object_id: str, distance: float) -> RepairOutcome:
        raise NotImplementedError("engine.merge_by_distance: not implemented")

    def fill_holes(self, object_id: str, max_sides: int = 0) -> RepairOutcome:
        raise NotImplementedError("engine.fill_holes: not implemented")
