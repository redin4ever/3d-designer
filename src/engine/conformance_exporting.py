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

import pytest

from contracts import EngineProtocol, Transform, Vec3

__all__ = [
    "check_export_scale_moves_objects_as_well_as_resizing_them",
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


def check_export_scale_moves_objects_as_well_as_resizing_them(engine, tmp_path) -> None:
    """A two-object scene must keep its proportions through a unit conversion.

    Export scaled each object in place while leaving its position in metres, so one object
    came out right and two came out at the wrong distance apart — 3.57x for Roblox studs,
    100x for Unreal centimetres. A single-object smoke export cannot see it, which is
    exactly what every earlier test did.

    Reads the node translations back out of the written GLB rather than recomputing the
    conversion, so it tests the exporter instead of restating the arithmetic.
    """
    engine.create_primitive("near", "cube", Vec3(1, 1, 1))
    engine.create_primitive("far", "cube", Vec3(1, 1, 1), Transform(translation=Vec3(10, 0, 0)))

    scale = 1.0 / 0.28  # metres -> Roblox studs
    path = str(tmp_path / "scaled.glb")
    engine.export_gltf(["near", "far"], path, y_up=True, scale=scale)

    translations = _glb_node_translations(path)
    assert len(translations) >= 2, f"expected two nodes in the GLB, got {len(translations)}"

    xs = sorted(t[0] for t in translations)
    separation = xs[-1] - xs[0]
    expected = 10.0 * scale
    assert separation == pytest.approx(expected, rel=1e-3), (
        f"objects 10m apart exported {separation:.3f} apart, expected {expected:.3f} — "
        "the translation did not receive the unit conversion the mesh did"
    )


def _glb_node_translations(path: str) -> list[tuple[float, float, float]]:
    """Node translations out of a binary glTF, without a parser dependency.

    GLB is a 12-byte header then length-prefixed chunks; the first is the JSON scene
    description. Reading it directly is a dozen lines and means this check tests the file
    that was actually written rather than the intent behind it.
    """
    import json
    import struct

    data = Path(path).read_bytes()
    assert data[:4] == b"glTF", "not a GLB file"
    offset = 12
    chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
    assert chunk_type == 0x4E4F534A, "first GLB chunk is not JSON"
    doc = json.loads(data[offset + 8 : offset + 8 + chunk_len].decode("utf-8"))
    return [tuple(n.get("translation", (0.0, 0.0, 0.0))) for n in doc.get("nodes", [])]
