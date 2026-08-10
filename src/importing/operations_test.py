"""Tests for the model-import operation boundary.

If these tests fail, an imported model can either leak an opaque engine failure to the
agent or fail to become one undo barrier with the complete set of created objects.
"""

from __future__ import annotations

import pytest

from contracts import ModelImportResult, Operation, RuleError
from importing import IMPORT_OPERATION_KIND, import_model_file, make_import_operation


class _ImportEngine:
    """Small engine seam that records the normalized import request."""

    def __init__(self, result: ModelImportResult | None = None) -> None:
        self.result = result or ModelImportResult(("house", "roof"), ("camera ignored",))
        self.calls: list[tuple[str, str, float, bool]] = []

    def import_model(
        self,
        path: str,
        *,
        source_up: str = "AUTO",
        unit_scale: float = 1.0,
        flatten: bool = True,
    ) -> ModelImportResult:
        self.calls.append((path, source_up, unit_scale, flatten))
        return self.result


def test_import_reports_every_created_object_and_engine_warning_as_an_assumption(tmp_path):
    """An agent must receive every imported id and every ignored-content warning."""
    source = tmp_path / "house.glb"
    source.write_bytes(b"placeholder")
    engine = _ImportEngine()
    op = Operation(
        op_id="import-1",
        kind=IMPORT_OPERATION_KIND,
        params={
            "path": str(source),
            "source_up": "Y",
            "unit_scale": 0.01,
            "flatten": False,
        },
        opaque=True,
    )

    result = import_model_file(engine, op)

    assert result.ok is True
    assert result.produced_objects == ("house", "roof")
    assert result.assumptions == ("camera ignored",)
    assert engine.calls == [(str(source), "Y", 0.01, False)]


def test_import_rejects_remote_paths_with_a_named_rule(tmp_path):
    """Remote URLs must never reach the local Blender import boundary."""
    with pytest.raises(RuleError) as exc_info:
        import_model_file(
            _ImportEngine(),
            Operation(
                op_id="import-remote",
                kind=IMPORT_OPERATION_KIND,
                params={"path": "https://example.com/house.glb"},
                opaque=True,
            ),
        )

    assert exc_info.value.rule == "import.local_path_required"


def test_import_rejects_missing_or_unsupported_files_by_name(tmp_path):
    """A bad local source must fail before the engine can partially mutate the scene."""
    missing = tmp_path / "missing.glb"
    with pytest.raises(RuleError) as missing_info:
        import_model_file(
            _ImportEngine(),
            Operation(
                op_id="import-missing",
                kind=IMPORT_OPERATION_KIND,
                params={"path": str(missing)},
                opaque=True,
            ),
        )
    assert missing_info.value.rule == "import.file_not_found"

    unsupported = tmp_path / "house.blend"
    unsupported.write_bytes(b"placeholder")
    with pytest.raises(RuleError) as unsupported_info:
        import_model_file(
            _ImportEngine(),
            Operation(
                op_id="import-unsupported",
                kind=IMPORT_OPERATION_KIND,
                params={"path": str(unsupported)},
                opaque=True,
            ),
        )
    assert unsupported_info.value.rule == "import.unsupported_format"


def test_import_rejects_non_positive_unit_scale_by_name(tmp_path):
    """Zero or negative scale must not reach an engine with ambiguous units."""
    source = tmp_path / "house.obj"
    source.write_bytes(b"placeholder")
    with pytest.raises(RuleError) as exc_info:
        import_model_file(
            _ImportEngine(),
            Operation(
                op_id="import-scale",
                kind=IMPORT_OPERATION_KIND,
                params={"path": str(source), "unit_scale": 0},
                opaque=True,
            ),
        )

    assert exc_info.value.rule == "import.invalid_unit_scale"


def test_import_operation_helper_marks_one_opaque_undo_barrier(tmp_path):
    """The main wiring helper must make import history opaque before dispatching it."""
    source = tmp_path / "house.gltf"
    op = make_import_operation("import-2", str(source), source_up="Z", unit_scale=2.0)

    assert op.kind == IMPORT_OPERATION_KIND
    assert op.opaque is True
    assert op.params == {
        "path": str(source),
        "source_up": "Z",
        "unit_scale": 2.0,
        "flatten": True,
    }
