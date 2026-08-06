"""F-016 — the unit constants in ``contracts.PROFILES``, pinned against each engine's own
documentation and against the bytes of a real exported ``.glb``.

Why this file exists separately from ``conversion_test.py``: every other test in this module
proves the conversion *plumbing* (axis remap, handedness, the round trip). None of them can
tell whether ``metres_per_unit`` is the right *number*, because they all read that number
from the same table the code under test reads it from. A test that divides by
``profile.metres_per_unit`` and asserts the result equals a division by
``profile.metres_per_unit`` passes for any value whatsoever — including a wrong one. So the
figures below are written as literals with a citation, and the measured side is read back out
of an actual exported file rather than recomputed.

This is also the only file in ``src/export/`` that needs Blender. ``test_documented_*`` and
``test_roblox_mass_unit_*`` run everywhere; the export tests carry ``needs_blender`` and the
root ``conftest.py`` skips them when ``bpy`` is not importable.

============================ THE CITATIONS ============================

ROBLOX — 1 stud = 28 cm, i.e. metres_per_unit = 0.28.
  https://create.roblox.com/docs/physics/units          (checked 2026-08-06)
    Unit conversion table, verbatim: "Length | 1 stud | 28 cm"; "Mass | 1 RMU | 21.952 kg".
  https://create.roblox.com/docs/resources/beyond-the-dark/building-architecture
                                                        (checked 2026-08-06)
    "The closest real-world scale for a single stud in Roblox is 28 centimeters."
  Read carefully, per F-016's warning, this is a LENGTH-UNIT figure, not the visual stud
  spacing on a part's surface and not a humanoid-proportion rule of thumb: it is the row of
  Roblox's own unit table that defines the length unit, and the mass row is derived from it
  (see ``test_roblox_mass_unit_corroborates_the_stud_length``). Roblox does state it as a
  recommended standard rather than an immutable engine constant — a project may reinterpret
  a stud as any length provided it stays internally consistent — but 0.28 m is the
  interpretation Roblox's own physics units are built around, and therefore the only correct
  default for this tool.
  It matters because Studio imports mesh units 1:1 as studs (same page: incoming units are
  converted "directly to studs without scaling"), so a 2 m door exported at 1 unit = 1 m
  arrives 2 studs tall — 56 cm in Roblox's own scale, roughly knee height on an avatar.
  Dividing by 0.28 is what makes it arrive at the size the user asked for.

UNITY — 1 unit = 1 m, i.e. metres_per_unit = 1.0.
  https://docs.unity3d.com/560/Documentation/Manual/class-Rigidbody.html
                                                        (checked 2026-08-06)
    "Unity's Physics Engine is scaled as 1 unit equals 1 metre."

UNREAL — 1 uu = 1 cm, i.e. metres_per_unit = 0.01.
  https://dev.epicgames.com/documentation/en-us/unreal-engine/world-settings-in-unreal-engine
                                                        (checked 2026-08-06)
    "Unreal Engine's coordinate system is based on a set scale where 1 Unreal Unit is 1
    centimeter."

GODOT — 1 unit = 1 m, i.e. metres_per_unit = 1.0.
  https://docs.godotengine.org/en/stable/tutorials/3d/introduction_to_3d.html
                                                        (checked 2026-08-06)
    "Godot uses the metric system for everything in 3D, with 1 unit being equal to 1 meter."
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from contracts import PROFILES, Vec3

from engine import BlenderEngine
from export import export_scene

#: Metres per one unit of the target engine, taken from each engine's own documentation
#: quoted in this module's docstring — NOT from ``contracts.PROFILES``. Reading the value
#: from the table under test is what made every previous check of this vacuous.
DOCUMENTED_METRES_PER_UNIT: dict[str, float] = {
    "roblox": 0.28,
    "unity": 1.0,
    "unreal": 0.01,
    "godot": 1.0,
}

#: A deliberately unequal box: a cube cannot distinguish a correct conversion from one that
#: swaps two axes, and equal extents would also hide a per-axis scale error.
BOX_METRES = Vec3(2.0, 1.0, 0.5)


# --------------------------------------------------------------------------- GLB reader
# Minimal binary-glTF reader. Deliberately not a recomputation of anything in ``export`` —
# it opens the file the exporter wrote and decodes the float32 vertex positions out of the
# binary chunk, then places them in world space through the scene graph, because Blender's
# glTF exporter is free to leave the object's scale on the node instead of baking it into
# the vertices, and either choice must produce the same physical size.


def _chunks(path: Path) -> tuple[dict, bytes]:
    """The JSON scene description and the binary buffer of a ``.glb``."""
    data = path.read_bytes()
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF", f"{path} is not a binary glTF"

    offset, gltf, binary = 12, None, b""
    while offset < len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        body = data[offset + 8 : offset + 8 + chunk_len]
        if chunk_type == 0x4E4F534A:  # 'JSON'
            gltf = json.loads(body.decode("utf-8"))
        elif chunk_type == 0x004E4942:  # 'BIN\0'
            binary = body
        offset += 8 + chunk_len + (-chunk_len % 4)

    assert gltf is not None, f"{path} has no JSON chunk"
    return gltf, binary


def _positions(gltf: dict, binary: bytes, accessor_index: int) -> list[tuple[float, float, float]]:
    """Decode one ``VEC3``/``FLOAT`` accessor into a list of local-space points."""
    accessor = gltf["accessors"][accessor_index]
    assert accessor["type"] == "VEC3" and accessor["componentType"] == 5126, (
        f"POSITION accessor is {accessor['type']}/{accessor['componentType']}, expected "
        "VEC3/FLOAT — this reader cannot decode quantized positions"
    )
    view = gltf["bufferViews"][accessor["bufferView"]]
    stride = view.get("byteStride") or 12
    base = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [
        struct.unpack_from("<3f", binary, base + i * stride)
        for i in range(accessor["count"])
    ]


def _node_matrix(node: dict) -> list[float]:
    """A node's local transform as a row-major 4x4, from either ``matrix`` or TRS."""
    if "matrix" in node:  # glTF stores matrices column-major
        c = node["matrix"]
        return [c[0], c[4], c[8], c[12],
                c[1], c[5], c[9], c[13],
                c[2], c[6], c[10], c[14],
                c[3], c[7], c[11], c[15]]

    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    return [
        (1 - 2 * (y * y + z * z)) * sx, (2 * (x * y - z * w)) * sy, (2 * (x * z + y * w)) * sz, tx,
        (2 * (x * y + z * w)) * sx, (1 - 2 * (x * x + z * z)) * sy, (2 * (y * z - x * w)) * sz, ty,
        (2 * (x * z - y * w)) * sx, (2 * (y * z + x * w)) * sy, (1 - 2 * (x * x + y * y)) * sz, tz,
        0.0, 0.0, 0.0, 1.0,
    ]


def _matmul(a: list[float], b: list[float]) -> list[float]:
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def _transform(m: list[float], p: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = p
    return (
        m[0] * x + m[1] * y + m[2] * z + m[3],
        m[4] * x + m[5] * y + m[6] * z + m[7],
        m[8] * x + m[9] * y + m[10] * z + m[11],
    )


def glb_world_extents(path: Path) -> tuple[float, float, float]:
    """The world-space bounding-box extents of everything in a ``.glb``, in the file's own
    units. Walks the scene graph so a scale left on a node counts exactly as much as one
    baked into the vertices."""
    gltf, binary = _chunks(path)
    nodes = gltf.get("nodes", [])
    identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]

    world: list[tuple[float, float, float]] = []
    roots = gltf["scenes"][gltf.get("scene", 0)]["nodes"]
    stack = [(index, identity) for index in roots]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        matrix = _matmul(parent, _node_matrix(node))
        if "mesh" in node:
            for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
                for point in _positions(gltf, binary, primitive["attributes"]["POSITION"]):
                    world.append(_transform(matrix, point))
        stack.extend((child, matrix) for child in node.get("children", []))

    assert world, f"{path} contains no vertex positions at all"
    return tuple(max(p[i] for p in world) - min(p[i] for p in world) for i in range(3))


# --------------------------------------------------------------------------- the tests


@pytest.mark.parametrize("profile_name", sorted(DOCUMENTED_METRES_PER_UNIT))
def test_documented_unit_scale_is_what_the_profile_carries(profile_name: str) -> None:
    """If this fails, every asset this tool has ever exported for that engine is uniformly
    mis-scaled — a 2 m door arrives at the wrong physical size in the target engine and no
    amount of correct geometry upstream can save it. The expected numbers here come from the
    engines' own documentation (cited in this module's docstring), never from the table under
    test, so this is the one assertion in the module that can actually be wrong."""
    assert PROFILES[profile_name].metres_per_unit == DOCUMENTED_METRES_PER_UNIT[profile_name]


def test_roblox_mass_unit_corroborates_the_stud_length() -> None:
    """Independent corroboration that 0.28 is Roblox's real length unit rather than a
    community rounding of something else. Roblox's unit table gives 1 RMU = 21.952 kg on the
    same page as 1 stud = 28 cm; 21.952 is exactly the mass of a one-stud cube of water at
    1000 kg/m3 (0.28^3 x 1000). The two documented rows only agree at 0.28 — at 0.25 the mass
    unit would be 15.625 kg, at 0.30 it would be 27.0. If this fails, the constant has been
    changed to a value Roblox's own physics units contradict."""
    metres_per_stud = DOCUMENTED_METRES_PER_UNIT["roblox"]
    roblox_mass_unit_kg = 21.952  # create.roblox.com/docs/physics/units, checked 2026-08-06
    water_density_kg_per_m3 = 1000.0

    assert metres_per_stud**3 * water_density_kg_per_m3 == pytest.approx(roblox_mass_unit_kg)


@pytest.mark.needs_blender
@pytest.mark.parametrize("profile_name", sorted(DOCUMENTED_METRES_PER_UNIT))
def test_a_known_box_exports_at_the_documented_unit_scale(
    profile_name: str, tmp_path: Path
) -> None:
    """The end-to-end pin: a 2.0 x 1.0 x 0.5 m box goes through the real Blender exporter and
    the vertex positions are read back out of the written ``.glb``. If this fails, the file a
    user hands to their engine is the wrong size on disk — which is the only place it
    matters, and the thing no test that recomputes ``metres / metres_per_unit`` can see.

    Extents are compared sorted so this stays neutral about axis order and handedness: the
    up-axis remap and Unity's X mirror are verified in ``conversion_test.py`` and must not be
    re-litigated (or accidentally re-specified) here."""
    engine = BlenderEngine()
    engine.reset()
    try:
        engine.create_primitive("scale_probe", "cube", BOX_METRES)
        path = tmp_path / f"{profile_name}.glb"
        report = export_scene(engine, ["scale_probe"], str(path), profile_name=profile_name)
        assert report.ok and path.exists(), "export reported success without writing a file"

        metres_per_unit = DOCUMENTED_METRES_PER_UNIT[profile_name]
        expected = sorted(d / metres_per_unit for d in BOX_METRES.as_tuple())
        measured = sorted(glb_world_extents(path))

        assert measured == pytest.approx(expected, rel=1e-4), (
            f"a {BOX_METRES.as_tuple()} m box exported to {profile_name} measures "
            f"{tuple(round(v, 4) for v in measured)} in the written .glb, expected "
            f"{tuple(round(v, 4) for v in expected)} at the documented "
            f"1 unit = {metres_per_unit} m"
        )
    finally:
        engine.reset()
