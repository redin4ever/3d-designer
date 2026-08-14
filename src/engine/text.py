"""Portable text-mesh creation for the Blender backend."""

from __future__ import annotations

from contracts import EngineError, Transform

from ._shared import apply_transform_fields, link_new_object

__all__ = ["TextOpsMixin"]


class TextOpsMixin:
    def create_text(
        self,
        object_id: str,
        text: str,
        height: float,
        depth: float,
        transform: Transform | None = None,
    ) -> str:
        import bpy

        if not text.strip():
            raise EngineError(
                "engine.empty_text",
                "text geometry needs at least one visible character",
                "pass a non-empty sign label",
            )
        if height <= 0 or depth <= 0:
            raise EngineError(
                "engine.bad_text_dimensions",
                "text height and depth must both be positive",
                "pass height > 0 and depth > 0",
            )

        curve = bpy.data.curves.new(f"{object_id}_font", "FONT")
        temporary = bpy.data.objects.new(f"{object_id}_font_source", curve)
        bpy.context.scene.collection.objects.link(temporary)
        mesh = None
        try:
            curve.body = text
            curve.align_x = "CENTER"
            curve.align_y = "CENTER"
            curve.size = 1.0
            curve.extrude = 0.5
            curve.resolution_u = 2
            curve.bevel_resolution = 0

            bpy.context.view_layer.update()
            evaluated = temporary.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = bpy.data.meshes.new_from_object(evaluated)

            xs = [vertex.co.x for vertex in mesh.vertices]
            ys = [vertex.co.y for vertex in mesh.vertices]
            zs = [vertex.co.z for vertex in mesh.vertices]
            if not xs or max(ys) - min(ys) <= 1e-9 or max(zs) - min(zs) <= 1e-9:
                raise EngineError(
                    "engine.invalid_text_geometry",
                    "the selected font produced degenerate geometry",
                    "use visible characters supported by the active font",
                )

            centre_x = (min(xs) + max(xs)) / 2
            centre_y = (min(ys) + max(ys)) / 2
            centre_z = (min(zs) + max(zs)) / 2
            planar_scale = height / (max(ys) - min(ys))
            depth_scale = depth / (max(zs) - min(zs))
            for vertex in mesh.vertices:
                vertex.co.x = (vertex.co.x - centre_x) * planar_scale
                vertex.co.y = (vertex.co.y - centre_y) * planar_scale
                vertex.co.z = (vertex.co.z - centre_z) * depth_scale
            mesh.update()

            obj = link_new_object(object_id, mesh)
            apply_transform_fields(obj, transform or Transform())
            mesh = None  # ownership transferred to the linked object
            return obj.name
        finally:
            bpy.data.objects.remove(temporary, do_unlink=True)
            if curve.users == 0:
                bpy.data.curves.remove(curve)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
