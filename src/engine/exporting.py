"""Stub ``ExportOps`` — writes glTF/GLB via Blender's own exporter.

Raises. See ``src/engine/mesh.py`` for why. When implemented, every parameter here
(``y_up``, ``mirror_x``, ``negate_rotation``, ``scale``) must reach Blender's exporter
untouched — the profile-table *decision* stays in ``src/export/``, this method only carries
the answer through. See ``ExportOps.export_gltf`` in ``src/contracts/engine.py``.
"""

from __future__ import annotations

from typing import Sequence

__all__ = ["ExportingMixin"]


class ExportingMixin:
    """``ExportOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def export_gltf(
        self,
        object_ids: Sequence[str],
        path: str,
        *,
        y_up: bool,
        mirror_x: bool = False,
        negate_rotation: bool = False,
        scale: float = 1.0,
        apply_modifiers: bool = True,
    ) -> str:
        raise NotImplementedError("engine.export_gltf: not implemented")
