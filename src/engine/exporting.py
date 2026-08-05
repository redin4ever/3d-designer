"""``ExportOps`` — writes glTF/GLB via Blender's own exporter.

Blender's glTF exporter (verified at runtime against this bpy build) has no
``mirror_x``/``negate_rotation``/``scale`` parameters of its own — only ``export_yup`` and
``export_apply``. Those three conversions are therefore applied here, to temporary duplicate
objects built for the export and discarded immediately after, rather than to the caller's
live objects: non-destructive, and avoids the exact "mutate the live transform and revert"
pattern ``ExportOps.export_gltf``'s docstring calls out as destructive and lock-requiring.
Only the resulting transform reaches the exporter; the actual glTF/PBR writing is entirely
delegated, per the docstring on ``ExportOps.export_gltf`` in ``src/contracts/engine.py``.
"""

from __future__ import annotations

from typing import Sequence

from contracts import EngineError, Quat, Transform, Vec3

from ._shared import get_object, read_transform_fields

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
        import bpy

        if not object_ids:
            raise EngineError(
                "engine.nothing_to_export", "no objects were selected for export",
                "pass at least one object id",
            )
        if scale <= 0:
            raise EngineError("engine.bad_export_scale", f"scale {scale} must be positive")

        temp_ids: list[str] = []
        try:
            for oid in object_ids:
                src = get_object(oid)  # raises engine.unknown_object
                t = read_transform_fields(src)
                new_scale = Vec3(
                    t.scale.x * scale * (-1.0 if mirror_x else 1.0),
                    t.scale.y * scale,
                    t.scale.z * scale,
                )
                new_rotation = (
                    Quat(t.rotation.w, -t.rotation.x, -t.rotation.y, -t.rotation.z)
                    if negate_rotation else t.rotation
                )
                temp_transform = Transform(translation=t.translation, rotation=new_rotation, scale=new_scale)
                temp_ids.append(self.duplicate(oid, f"__export__{oid}", temp_transform))

            for obj in bpy.data.objects:
                obj.select_set(False)
            for tid in temp_ids:
                bpy.data.objects[tid].select_set(True)
            bpy.context.view_layer.objects.active = bpy.data.objects[temp_ids[0]]

            export_format = "GLB" if path.lower().endswith(".glb") else "GLTF_EMBEDDED"
            bpy.ops.export_scene.gltf(
                filepath=path,
                export_format=export_format,
                use_selection=True,
                export_yup=y_up,
                export_apply=apply_modifiers,
            )
        finally:
            for tid in temp_ids:
                if self.exists(tid):
                    self.delete(tid)

        return path
