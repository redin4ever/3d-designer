"""Material, UV, bake and export halves of :class:`FakeEngine`.

Split from the mesh/modifier core because it is a distinct actor — surfacing rather than
geometry — and because it is where the one interesting failure lives: ``bake`` can raise
:class:`EngineUnavailable`, since baking generally needs a windowed Blender context that
in-process ``bpy`` does not have. Tests that need to exercise that path construct the
engine with ``bake_supported=False``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from contracts import (
    EngineError,
    EngineUnavailable,
    ModelImportResult,
    SUPPORTED_MODEL_EXTENSIONS,
    Vec3,
)

__all__ = ["FakeSurfacingMixin"]


class FakeSurfacingMixin:
    """Requires ``_get``, ``_record``, ``world_bounds`` and ``_bake_supported`` from the
    core. Kept as a mixin rather than a collaborator because these operations mutate the
    same object records the core owns; a collaborator would need the core's internals,
    which is the definition of a false seam."""

    # -------------------------------------------------------------- materials

    def create_material(self, name: str, base_color: tuple[float, float, float]) -> str:
        self._materials[name] = {"base_color": base_color, "roughness": 0.5, "metallic": 0.0}
        self._record("create_material", name)
        return name

    def set_pbr(
        self,
        material_id: str,
        *,
        base_color: tuple[float, float, float] | None = None,
        roughness: float | None = None,
        metallic: float | None = None,
    ) -> None:
        if material_id not in self._materials:
            raise EngineError(
                "engine.unknown_material",
                f"no material named {material_id!r}",
                f"known: {', '.join(sorted(self._materials)) or '(none)'}",
            )
        mat = self._materials[material_id]
        if base_color is not None:
            mat["base_color"] = base_color
        if roughness is not None:
            mat["roughness"] = roughness
        if metallic is not None:
            mat["metallic"] = metallic
        self._record("set_pbr", material_id)

    def material(self, material_id: str) -> dict:
        """Test-only accessor — not part of ``EngineProtocol``. Lets a detail-pass test
        assert that roughness actually varies across a surface rather than asserting that
        ``set_pbr`` was called."""
        return dict(self._materials[material_id])

    def assign_material(self, object_id: str, material_id: str, slot: int = 0) -> None:
        obj = self._get(object_id)
        if material_id not in self._materials:
            raise EngineError("engine.unknown_material", f"no material named {material_id!r}")
        while len(obj.materials) <= slot:
            obj.materials.append("")
        obj.materials[slot] = material_id
        self._record("assign_material", object_id, material_id, slot)

    def create_texture_material(self, material: object) -> str:
        name = getattr(material, "name", "")
        if not name:
            raise EngineError("engine.bad_material", "texture material has no name")
        definition = material.to_dict() if callable(getattr(material, "to_dict", None)) else {}
        self._materials[name] = {"base_color": (0.8, 0.8, 0.8), "roughness": 0.5,
                                 "metallic": 0.0, "texture": definition}
        self._record("create_texture_material", name)
        return name

    def assign_texture_material(
        self, object_id: str, material_id: str, slot: int = 0, material: object | None = None
    ) -> None:
        if material is not None and material_id not in self._materials:
            self.create_texture_material(material)
        self.assign_material(object_id, material_id, slot)

    # -------------------------------------------------------------- uv and bake

    def unwrap(self, object_id: str, *, method: str = "angle_based", margin: float = 0.001) -> None:
        obj = self._get(object_id)
        bounds = self.world_bounds(object_id)
        size = bounds.size
        sx = size.x if size.x > 1e-9 else 1.0
        sy = size.y if size.y > 1e-9 else 1.0
        # A planar XY projection. Enough for tests asserting UVs exist and stay in [0,1];
        # nothing should assert on the exact layout, which is Blender's business.
        obj.uvs = [
            (
                (obj.transform.apply(v).x - bounds.minimum.x) / sx,
                (obj.transform.apply(v).y - bounds.minimum.y) / sy,
            )
            for v in obj.vertices
        ]
        obj.unwrapped = True
        self._record("unwrap", object_id, method, margin)

    def mark_seams(self, object_id: str, edge_indices: Sequence[int]) -> None:
        obj = self._get(object_id)
        obj.seams.update(edge_indices)
        self._record("mark_seams", object_id, tuple(edge_indices))

    def bake(
        self, object_id: str, channels: Sequence[str], resolution: int, output_dir: str
    ) -> dict[str, str]:
        if not self._bake_supported:
            raise EngineUnavailable("bake")
        obj = self._get(object_id)
        if not obj.unwrapped:
            raise EngineError(
                "engine.not_unwrapped",
                f"{object_id} has no UVs",
                "call unwrap() before bake()",
            )
        if resolution <= 0 or resolution & (resolution - 1):
            raise EngineError(
                "engine.bad_resolution",
                f"resolution {resolution} is not a positive power of two",
                "use 512, 1024, 2048 or 4096",
            )
        self._record("bake", object_id, tuple(channels), resolution)
        return {c: f"{output_dir}/{object_id}_{c}.png" for c in channels}

    # -------------------------------------------------------------- export

    def import_model(
        self,
        path: str,
        *,
        source_up: str = "AUTO",
        unit_scale: float = 1.0,
        flatten: bool = True,
    ) -> ModelImportResult:
        """Bookkeep a deterministic placeholder mesh; the fake never parses asset bytes."""
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED_MODEL_EXTENSIONS:
            raise EngineError(
                "engine.unsupported_import_format",
                f"{suffix or '(none)'} is not a supported model format",
                f"use one of: {', '.join(SUPPORTED_MODEL_EXTENSIONS)}",
            )
        if unit_scale <= 0:
            raise EngineError(
                "engine.bad_import_scale", f"unit scale {unit_scale} must be positive",
                "pass a positive metres-per-source-unit multiplier",
            )
        if source_up.upper() not in {"AUTO", "X", "Y", "Z"}:
            raise EngineError(
                "engine.bad_import_axis", f"source up axis {source_up!r} is invalid",
                "use AUTO, X, Y, or Z",
            )
        if not source.is_file():
            raise EngineError(
                "engine.import_file_missing", f"model file does not exist: {source}",
                "pass an existing local file path",
            )

        size = float(unit_scale)
        object_id = self.create_mesh(
            source.stem or "Imported",
            (Vec3(0, 0, 0), Vec3(size, 0, 0), Vec3(0, size, 0)),
            ((0, 1, 2),),
        )
        self._record("import_model", str(source), suffix, source_up.upper(), unit_scale, flatten)
        return ModelImportResult(object_ids=(object_id,))

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
        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_MODEL_EXTENSIONS:
            raise EngineError(
                "engine.unsupported_export_format",
                f"{suffix or '(none)'} is not a supported model format",
                f"use one of: {', '.join(SUPPORTED_MODEL_EXTENSIONS)}",
            )
        if not object_ids:
            raise EngineError(
                "engine.nothing_to_export", "no objects were selected for export",
                "pass at least one object id",
            )
        if scale <= 0:
            raise EngineError("engine.bad_export_scale", f"scale {scale} must be positive")
        for oid in object_ids:
            self._get(oid)
        self._record(
            "export_model", tuple(object_ids), path, suffix, y_up, mirror_x,
            negate_rotation, scale, apply_modifiers,
        )
        return path

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
        if not object_ids:
            raise EngineError(
                "engine.nothing_to_export",
                "no objects were selected for export",
                "pass at least one object id",
            )
        if scale <= 0:
            raise EngineError("engine.bad_export_scale", f"scale {scale} must be positive")
        for oid in object_ids:
            self._get(oid)
        # Recorded in full so an export test can assert the whole conversion reached the
        # exporter — a left-handed target needs mirror_x AND negate_rotation together, and
        # sending one without the other is the silent round-trip mirroring bug.
        self._record("export_gltf", tuple(object_ids), path, y_up, mirror_x, negate_rotation, scale)
        return path

    # -------------------------------------------------------------- raw

    def execute(self, source: str, namespace: dict | None = None) -> dict:
        """Unrestricted, by explicit decision (ADR-009). No sandbox, no allowlist.

        The fake behaves exactly like the real thing here on purpose: a test that proves
        raw execution is recorded as an undo barrier must run against something that
        actually executes.
        """
        ns = dict(namespace or {})
        ns.setdefault("engine", self)
        exec(source, ns)  # noqa: S102 — this is the module's entire purpose
        self._record("execute", source[:64])
        return ns
