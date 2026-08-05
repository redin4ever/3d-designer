"""Conformance checks for ``ExportOps.export_gltf``.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/exporting.py``.
``check_export_gltf_writes_a_nonempty_file`` is Blender-only — see ``conformance.py``'s
module docstring for why ``FakeEngine`` is exempt (it never touches the filesystem; it only
records the call). ``check_export_gltf_threads_the_full_conversion_through`` is universal —
added in response to a conformance audit — and handles the fake/real split itself, since
"the observable difference" means something different on each side.
"""

from __future__ import annotations

from pathlib import Path

from contracts import EngineProtocol, Vec3

__all__ = [
    "check_export_gltf_writes_a_nonempty_file",
    "check_export_gltf_threads_the_full_conversion_through",
]


def check_export_gltf_writes_a_nonempty_file(engine: EngineProtocol, tmp_path: Path) -> None:
    """``export_gltf`` returning a path with nothing on disk at it is worse than raising —
    the caller reports success and the exported asset does not exist."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    out = tmp_path / "box.glb"

    engine.export_gltf([oid], str(out), y_up=True)

    assert out.exists(), "export_gltf returned without writing a file the caller can serve"
    assert out.stat().st_size > 0, "export_gltf wrote an empty file"


def check_export_gltf_threads_the_full_conversion_through(
    engine: EngineProtocol, tmp_path: Path
) -> None:
    """Added in response to a conformance audit: the check above only ever passes
    ``y_up=True`` and leaves ``mirror_x``, ``negate_rotation`` and ``scale`` at their
    defaults, so an implementation that accepts those keywords and silently drops them
    before calling the real exporter would still pass every existing export check — exactly
    the silent round-trip mirroring bug those parameters exist to prevent (see
    ``ExportOps.export_gltf``'s docstring). Exports the same cube twice, once with every
    non-default conversion parameter set, and asserts the two outputs differ. For
    ``FakeEngine`` there is no real file to diff (it never touches the filesystem), so the
    recorded call arguments are the observable difference instead; for the real engine the
    file bytes are."""
    oid = engine.create_primitive("convbox", "cube", Vec3(1, 1, 1))
    default_path = tmp_path / "default.glb"
    converted_path = tmp_path / "converted.glb"

    engine.export_gltf([oid], str(default_path), y_up=True)
    engine.export_gltf(
        [oid], str(converted_path), y_up=True,
        mirror_x=True, negate_rotation=True, scale=1 / 0.28,
    )

    calls = getattr(engine, "calls", None)
    if calls is not None:
        export_calls = [c for c in calls if c[0] == "export_gltf"]
        assert len(export_calls) >= 2, "expected two recorded export_gltf calls"
        _, _, _, mirror_a, negate_a, scale_a = export_calls[-2][1]
        _, _, _, mirror_b, negate_b, scale_b = export_calls[-1][1]
        assert (mirror_a, negate_a, scale_a) != (mirror_b, negate_b, scale_b), (
            "recorded mirror_x/negate_rotation/scale were identical across two differently "
            "configured export_gltf calls — the parameters never reached the exporter"
        )
    else:
        default_bytes = default_path.read_bytes()
        converted_bytes = converted_path.read_bytes()
        assert default_bytes != converted_bytes, (
            "export_gltf produced byte-identical output for different mirror_x/"
            "negate_rotation/scale — those parameters were silently dropped before "
            "reaching the exporter"
        )
