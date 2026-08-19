"""Blender 5.2 model import/export, including non-destructive native append.

All advertised GLB/glTF, FBX, OBJ, STL, PLY, USD, USDA, and USDC suffixes are exercised
against their real Blender operators. The ``wm`` exporters use Blender 5's long-form axis
enums while FBX retains its legacy axis keyword family.

This file deliberately contains no composition-root changes.  ``ModelIOMixin`` is the
engine-side implementation of the frozen ``ImportOps``/``ExportOps`` contract and is
mixed into the concrete engine by the integration change that owns ``session.py``.

Import is treated as a transaction over the objects Blender creates: the pre-import object
set is recorded, and every newly-created object is removed again if the operator or any
post-processing step fails.  Export uses detached object/data copies and restores Blender's
selection state, so conversion never mutates a live modelling object.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from contracts import (
    EngineError,
    ModelImportResult,
    SUPPORTED_MODEL_EXPORT_EXTENSIONS,
    SUPPORTED_MODEL_IMPORT_EXTENSIONS,
)

__all__ = [
    "ModelIOMixin",
    "export_operator_for_suffix",
    "import_operator_for_suffix",
]


_IMPORT_OPERATORS: dict[str, str] = {
    ".glb": "import_scene.gltf",
    ".gltf": "import_scene.gltf",
    ".fbx": "import_scene.fbx",
    ".obj": "wm.obj_import",
    ".stl": "wm.stl_import",
    ".ply": "wm.ply_import",
    ".usd": "wm.usd_import",
    ".usda": "wm.usd_import",
    ".usdc": "wm.usd_import",
}

_EXPORT_OPERATORS: dict[str, str] = {
    ".glb": "export_scene.gltf",
    ".gltf": "export_scene.gltf",
    ".fbx": "export_scene.fbx",
    ".obj": "wm.obj_export",
    ".stl": "wm.stl_export",
    ".ply": "wm.ply_export",
    ".usd": "wm.usd_export",
    ".usda": "wm.usd_export",
    ".usdc": "wm.usd_export",
}

_VALID_SOURCE_UP = frozenset(("AUTO", "X", "Y", "Z"))


def _normalise_suffix(value: str) -> str:
    suffix = str(value).lower()
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix


def import_operator_for_suffix(suffix: str) -> str:
    """Return the Blender operator id for one supported import suffix."""

    key = _normalise_suffix(suffix)
    try:
        return _IMPORT_OPERATORS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported model import suffix: {suffix!r}") from exc


def export_operator_for_suffix(suffix: str) -> str:
    """Return the Blender operator id for one supported export suffix."""

    key = _normalise_suffix(suffix)
    try:
        return _EXPORT_OPERATORS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported model export suffix: {suffix!r}") from exc


def _operator(bpy: Any, operator_id: str):
    group, name = operator_id.split(".", 1)
    return getattr(getattr(bpy.ops, group), name)


def _axis_conversion(source_up: str):
    """Return a matrix mapping the declared source up axis to internal Z-up."""

    from mathutils import Matrix

    if source_up in ("AUTO", "Z"):
        return Matrix.Identity(4)
    if source_up == "X":
        # Blender's Y rotation by -90 degrees maps source +X to internal +Z.
        return Matrix.Rotation(-math.pi / 2.0, 4, "Y")
    # A +90 degree X rotation maps source +Y to internal +Z.
    return Matrix.Rotation(math.pi / 2.0, 4, "X")


def _scale_matrix(unit_scale: float):
    from mathutils import Matrix

    return Matrix.Scale(unit_scale, 4)


def _remove_object(obj: Any) -> None:
    import bpy

    if obj.name in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)


def _remove_created_objects(objects: Sequence[Any]) -> None:
    """Remove objects and orphaned data created by a failed import/export transaction."""

    import bpy

    meshes = {obj.data for obj in objects if getattr(obj, "data", None) is not None}
    for obj in list(objects):
        _remove_object(obj)
    for mesh in meshes:
        if mesh is not None and mesh.users == 0 and mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)


def _new_datablock_snapshot(bpy: Any) -> dict[str, set[Any]]:
    return {
        "meshes": set(bpy.data.meshes),
        "materials": set(bpy.data.materials),
        "images": set(bpy.data.images),
        "curves": set(bpy.data.curves),
        "cameras": set(bpy.data.cameras),
        "lights": set(bpy.data.lights),
    }


def _purge_new_orphans(bpy: Any, before: dict[str, set[Any]]) -> None:
    collections = {
        "meshes": bpy.data.meshes,
        "materials": bpy.data.materials,
        "images": bpy.data.images,
        "curves": bpy.data.curves,
        "cameras": bpy.data.cameras,
        "lights": bpy.data.lights,
    }
    for kind, datablocks in collections.items():
        for block in list(datablocks):
            if block in before[kind] or getattr(block, "users", 1) != 0:
                continue
            try:
                datablocks.remove(block)
            except RuntimeError:
                pass


def _import_kwargs(suffix: str) -> dict[str, object]:
    """Use conservative Blender 5.2 options; conversion is applied after import."""

    if suffix in (".glb", ".gltf"):
        return {"import_select_created_objects": False}
    if suffix == ".usd" or suffix in (".usda", ".usdc"):
        return {
            "import_meshes": True,
            "import_materials": True,
            "import_cameras": True,
            "import_lights": True,
        }
    return {}


def _append_blend_objects(bpy: Any, source: Path) -> tuple[list[Any], tuple[str, ...]]:
    """Load native objects as local datablocks and link only meshes into this scene.

    ``open_mainfile`` is intentionally never used: it would replace the process scene and
    invalidate the live project. Loading every object lets Blender resolve dependencies and
    parent transforms; non-mesh objects are retained only long enough to report and detach.
    """

    with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
        loaded.objects = list(available.objects)
    objects = [obj for obj in loaded.objects if obj is not None]
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    ignored = sorted((obj.name, obj.type) for obj in objects if obj.type != "MESH")
    warnings = tuple(
        f"ignored imported non-mesh object {name!r} ({kind})" for name, kind in ignored
    )

    # A mesh may inherit from an empty/armature that is deliberately not imported. Preserve
    # its evaluated placement before detaching that relationship and removing the parent.
    worlds = {obj: obj.matrix_world.copy() for obj in mesh_objects}
    for obj in mesh_objects:
        if not obj.users_collection:
            bpy.context.scene.collection.objects.link(obj)
        obj.parent = None
        obj.matrix_world = worlds[obj]
    return objects, warnings


def _axis_export_kwargs(y_up: bool) -> dict[str, object]:
    if y_up:
        return {"axis_forward": "-Z", "axis_up": "Y"}
    return {"axis_forward": "-Y", "axis_up": "Z"}


def _wm_axis_export_kwargs(y_up: bool) -> dict[str, object]:
    """Blender 4+/5 ``wm`` exporters use long-form axis property names."""

    if y_up:
        return {"forward_axis": "NEGATIVE_Z", "up_axis": "Y"}
    return {"forward_axis": "NEGATIVE_Y", "up_axis": "Z"}


def _export_kwargs(suffix: str, *, y_up: bool, apply_modifiers: bool) -> dict[str, object]:
    if suffix in (".glb", ".gltf"):
        return {
            "export_format": "GLB" if suffix == ".glb" else "GLTF_SEPARATE",
            "use_selection": True,
            "export_yup": y_up,
            "export_apply": apply_modifiers,
        }
    if suffix == ".fbx":
        return {
            "use_selection": True,
            "object_types": {"MESH"},
            "use_mesh_modifiers": apply_modifiers,
            **_axis_export_kwargs(y_up),
        }
    if suffix in (".obj", ".stl", ".ply"):
        return {
            "export_selected_objects": True,
            "apply_modifiers": apply_modifiers,
            **_wm_axis_export_kwargs(y_up),
        }
    return {
        "selected_objects_only": True,
        "export_meshes": True,
        "export_lights": False,
        "export_cameras": False,
        "export_materials": True,
    }


class ModelIOMixin:
    """Blender 5.2 implementation of the frozen model file boundary."""

    def import_model(
        self,
        path: str,
        *,
        source_up: str = "AUTO",
        unit_scale: float = 1.0,
        flatten: bool = True,
    ) -> ModelImportResult:
        import bpy

        source_up = str(source_up).upper()
        if source_up not in _VALID_SOURCE_UP:
            raise EngineError(
                "engine.invalid_source_up",
                f"source_up {source_up!r} is not AUTO, X, Y, or Z",
                "use source_up='AUTO', 'X', 'Y', or 'Z'",
            )
        if not isinstance(unit_scale, (int, float)) or not math.isfinite(unit_scale) or unit_scale <= 0:
            raise EngineError(
                "engine.bad_import_scale",
                f"unit_scale {unit_scale!r} must be a finite positive number",
                "pass a positive scale from source units to metres",
            )

        source = Path(path)
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED_MODEL_IMPORT_EXTENSIONS:
            raise EngineError(
                "engine.unsupported_model_format",
                f"model suffix {suffix or '(none)'!r} is not supported",
                f"use one of {', '.join(SUPPORTED_MODEL_IMPORT_EXTENSIONS)}",
            )
        if not source.is_file():
            raise EngineError(
                "engine.model_file_missing",
                f"model file does not exist: {source}",
                "pass an existing local model file",
            )

        before_objects = set(bpy.data.objects)
        before_data = _new_datablock_snapshot(bpy)
        created: list[Any] = []
        try:
            warnings: tuple[str, ...] = ()
            if suffix == ".blend":
                created, warnings = _append_blend_objects(bpy, source)
            else:
                op = _operator(bpy, import_operator_for_suffix(suffix))
                op(filepath=str(source), **_import_kwargs(suffix))
                created = [obj for obj in bpy.data.objects if obj not in before_objects]
            mesh_objects = [obj for obj in created if obj.type == "MESH"]
            ignored = sorted((obj.name, obj.type) for obj in created if obj.type != "MESH")
            if suffix != ".blend":
                warnings = tuple(
                    f"ignored imported non-mesh object {name!r} ({kind})" for name, kind in ignored
                )
            if not mesh_objects:
                raise EngineError(
                    "engine.model_import_no_meshes",
                    f"{source.name!r} imported no mesh objects",
                    "choose a model file containing at least one mesh",
                )

            conversion = _axis_conversion(source_up) @ _scale_matrix(float(unit_scale))
            for obj in mesh_objects:
                world = conversion @ obj.matrix_world.copy()
                if flatten:
                    obj.data.transform(world)
                    obj.data.update()
                    obj.matrix_world.identity()
                else:
                    obj.matrix_world = world
            bpy.context.view_layer.update()

            if suffix == ".blend":
                _remove_created_objects([obj for obj in created if obj.type != "MESH"])
                _purge_new_orphans(bpy, before_data)

            # Blender's own name allocator is collision-safe. Sorting the actual names makes
            # result order deterministic without replacing or guessing a collision suffix.
            object_ids = tuple(sorted(obj.name for obj in mesh_objects))
            return ModelImportResult(object_ids=object_ids, warnings=warnings)
        except EngineError:
            _remove_created_objects(created or [obj for obj in bpy.data.objects if obj not in before_objects])
            _purge_new_orphans(bpy, before_data)
            raise
        except Exception as exc:
            _remove_created_objects(created or [obj for obj in bpy.data.objects if obj not in before_objects])
            _purge_new_orphans(bpy, before_data)
            raise EngineError(
                "engine.model_import_failed",
                f"Blender could not import {source.name!r}: {exc}",
                "verify the file is readable and valid for its declared format",
            ) from exc

    def export_model(
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
        from mathutils import Matrix

        if not object_ids:
            raise EngineError(
                "engine.nothing_to_export",
                "no objects were selected for export",
                "pass at least one mesh object id",
            )
        if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise EngineError(
                "engine.bad_export_scale",
                f"scale {scale!r} must be a finite positive number",
                "pass a positive export scale",
            )

        target = Path(path)
        suffix = target.suffix.lower()
        if suffix not in SUPPORTED_MODEL_EXPORT_EXTENSIONS:
            raise EngineError(
                "engine.unsupported_model_format",
                f"model suffix {suffix or '(none)'!r} is not supported",
                f"use one of {', '.join(SUPPORTED_MODEL_EXPORT_EXTENSIONS)}",
            )

        sources: list[Any] = []
        for object_id in object_ids:
            obj = bpy.data.objects.get(object_id)
            if obj is None or obj.type != "MESH":
                raise EngineError(
                    "engine.unknown_object",
                    f"no mesh object named {object_id!r}",
                    "pass ids returned by the scene object listing",
                )
            sources.append(obj)

        prior_selection = {obj: obj.select_get() for obj in bpy.data.objects}
        prior_active = bpy.context.view_layer.objects.active
        temporary: list[Any] = []
        try:
            for index, source in enumerate(sources):
                temp = source.copy()
                temp.data = source.data.copy()
                temp.name = f"__forge3d_export__{index:04d}__{source.name}"
                temp.parent = None
                bpy.context.scene.collection.objects.link(temp)
                temporary.append(temp)

                location, rotation, object_scale = source.matrix_world.decompose()
                location *= float(scale)
                object_scale *= float(scale)
                if mirror_x:
                    location.x *= -1.0
                    object_scale.x *= -1.0
                if negate_rotation:
                    rotation = rotation.conjugated()

                temp.rotation_mode = "QUATERNION"
                temp.location = location
                temp.rotation_quaternion = rotation
                temp.scale = object_scale

            for obj in bpy.data.objects:
                obj.select_set(False)
            for obj in temporary:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = temporary[0]
            bpy.context.view_layer.update()

            op = _operator(bpy, export_operator_for_suffix(suffix))
            op(filepath=str(target), **_export_kwargs(
                suffix, y_up=bool(y_up), apply_modifiers=bool(apply_modifiers)
            ))
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(
                "engine.model_export_failed",
                f"Blender could not export {target.name!r}: {exc}",
                "verify the destination is writable and the selected meshes are valid",
            ) from exc
        finally:
            for obj in temporary:
                mesh = obj.data
                _remove_object(obj)
                if mesh is not None and mesh.users == 0 and mesh.name in bpy.data.meshes:
                    bpy.data.meshes.remove(mesh)
            for obj, selected in prior_selection.items():
                if obj.name in bpy.data.objects:
                    obj.select_set(selected)
            if prior_active is not None and prior_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = prior_active
            else:
                bpy.context.view_layer.objects.active = None

        return str(path)
