"""The shared model-file boundary, frozen before engine/UI work starts."""

from __future__ import annotations

import contracts


def test_model_import_and_export_formats_are_distinct() -> None:
    assert contracts.SUPPORTED_MODEL_EXPORT_EXTENSIONS == (
        ".glb", ".gltf", ".fbx", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc",
    )
    assert contracts.SUPPORTED_MODEL_IMPORT_EXTENSIONS == (
        ".glb", ".gltf", ".fbx", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc",
        ".blend",
    )
    assert contracts.SUPPORTED_MODEL_EXTENSIONS == contracts.SUPPORTED_MODEL_EXPORT_EXTENSIONS


def test_engine_contract_exposes_atomic_model_import_and_generic_export() -> None:
    assert hasattr(contracts.EngineProtocol, "import_model")
    assert hasattr(contracts.EngineProtocol, "export_model")


def test_model_import_result_keeps_warnings_separate_from_created_meshes() -> None:
    result_type = getattr(contracts, "ModelImportResult", None)
    assert result_type is not None
    result = result_type(object_ids=("House",), warnings=("ignored Camera",))
    assert result.object_ids == ("House",)
    assert result.warnings == ("ignored Camera",)


def test_generic_profile_is_editor_safe_without_changing_the_agent_default() -> None:
    assert contracts.DEFAULT_PROFILE == "roblox"
    generic = contracts.profile_for("generic")
    assert generic.metres_per_unit == 1.0
    assert generic.up_axis.value == "Y"
    assert generic.handedness.value == "right"
