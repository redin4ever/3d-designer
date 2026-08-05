"""Stub ``MaterialOps`` + ``UVBakeOps`` — materials, unwrap, seams and bake.

Every method raises. See ``src/engine/mesh.py`` for why. ``bake`` is the one method this
whole module might legitimately never manage to satisfy on this machine: in-process ``bpy``
has no ``bpy.context.window`` (ADR-001), and baking generally needs one. When implemented,
``bake`` must raise :class:`contracts.EngineUnavailable` for that case — never propagate a
bare bpy exception — so callers get a named capability failure instead of a mystery
traceback. See ``conformance.check_bake_succeeds_or_raises_capability_error``.
"""

from __future__ import annotations

from typing import Sequence

__all__ = ["SurfacingMixin"]


class SurfacingMixin:
    """``MaterialOps`` + ``UVBakeOps`` surface, mixed into
    :class:`~engine.session.BlenderEngine`. Combined per the suggested file split: both are
    "surfacing" rather than geometry, and bake is UV-dependent."""

    # ---------------------------------------------------------------- materials

    def create_material(self, name: str, base_color: tuple[float, float, float]) -> str:
        raise NotImplementedError("engine.create_material: not implemented")

    def set_pbr(
        self,
        material_id: str,
        *,
        base_color: tuple[float, float, float] | None = None,
        roughness: float | None = None,
        metallic: float | None = None,
    ) -> None:
        raise NotImplementedError("engine.set_pbr: not implemented")

    def assign_material(self, object_id: str, material_id: str, slot: int = 0) -> None:
        raise NotImplementedError("engine.assign_material: not implemented")

    # ---------------------------------------------------------------- uv and bake

    def unwrap(self, object_id: str, *, method: str = "angle_based", margin: float = 0.001) -> None:
        raise NotImplementedError("engine.unwrap: not implemented")

    def mark_seams(self, object_id: str, edge_indices: Sequence[int]) -> None:
        raise NotImplementedError("engine.mark_seams: not implemented")

    def bake(
        self, object_id: str, channels: Sequence[str], resolution: int, output_dir: str
    ) -> dict[str, str]:
        raise NotImplementedError("engine.bake: not implemented")
