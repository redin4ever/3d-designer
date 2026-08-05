"""Conformance checks for ``ExportOps.export_gltf``.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/exporting.py``.
Blender-only — see ``conformance.py``'s module docstring for why ``FakeEngine`` is exempt
(it never touches the filesystem; it only records the call).
"""

from __future__ import annotations

from pathlib import Path

from contracts import EngineProtocol, Vec3

__all__ = ["check_export_gltf_writes_a_nonempty_file"]


def check_export_gltf_writes_a_nonempty_file(engine: EngineProtocol, tmp_path: Path) -> None:
    """``export_gltf`` returning a path with nothing on disk at it is worse than raising —
    the caller reports success and the exported asset does not exist."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    out = tmp_path / "box.glb"

    engine.export_gltf([oid], str(out), y_up=True)

    assert out.exists(), "export_gltf returned without writing a file the caller can serve"
    assert out.stat().st_size > 0, "export_gltf wrote an empty file"
