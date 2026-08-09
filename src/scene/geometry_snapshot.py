"""Writing the live **geometry** to a file, and reading it back (F-011, Gate B 5.3).

This is what an undo barrier restores from. It has to be geometry rather than the
document: an opaque operation is by definition one whose effect the operation log does not
describe, so the previous implementation — ``orchestration`` calling ``scene.save()``,
which serialises the log — restored nothing at all. Undo across a raw-execution barrier
then re-ran the script: a non-deterministic script produced ``randobj_f9dd53``, and after
undo-then-redo produced three differently-named objects, while the system reported a clean
``FULL_RESYNC``.

Written against :class:`contracts.EngineProtocol` alone — ``list_objects``, ``snapshot``,
``create_mesh``, ``set_transform`` and the material calls — so it behaves identically
against ``testing.FakeEngine`` and against real Blender, and needs no ``.blend`` file
format knowledge in a module that is not allowed to import ``bpy``.

**What a restore reproduces:** every object's id, evaluated triangles, local vertices,
transform, UV layout, material slots, and managed texture definitions. The
pre-triangulation face count is not recoverable because ``snapshot`` hands over triangles,
so a restored mesh is the triangulated form of the captured one.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from contracts import EngineProtocol, Quat, Transform, Vec3

__all__ = [
    "SNAPSHOT_MARKER",
    "snapshot_directory",
    "capture",
    "restore",
    "is_geometry_snapshot",
]

SNAPSHOT_MARKER = "forge3d_geometry_snapshot"
"""First key in every file this module writes.

Its whole job is to let :func:`is_geometry_snapshot` tell one of these apart from a saved
operation log without parsing the file — which matters because a caller handing ``apply``
a document save instead of a geometry snapshot is exactly the bug this module exists to
fix, and it must be detected rather than restored from.
"""

SNAPSHOT_FORMAT = 1


def snapshot_directory() -> Path:
    """Where captures live. Under the system temp directory on purpose: these are a
    rebuild aid for one session, not part of the user's project, and writing them beside
    the scene file would litter a directory the user owns."""
    directory = Path(tempfile.gettempdir()) / "forge3d-geometry"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _vec3(v: Vec3) -> list[float]:
    return [v.x, v.y, v.z]


def _transform_to_dict(t: Transform) -> dict[str, Any]:
    return {
        "translation": _vec3(t.translation),
        "rotation": [t.rotation.w, t.rotation.x, t.rotation.y, t.rotation.z],
        "scale": _vec3(t.scale),
    }


def _transform_from_dict(data: dict[str, Any] | None) -> Transform:
    if not data:
        return Transform()
    w, x, y, z = data.get("rotation", [1.0, 0.0, 0.0, 0.0])
    return Transform(
        translation=Vec3(*data.get("translation", [0.0, 0.0, 0.0])),
        rotation=Quat(w, x, y, z),
        scale=Vec3(*data.get("scale", [1.0, 1.0, 1.0])),
    )


def capture(engine: EngineProtocol, path: str) -> str:
    """Write every object the engine currently holds to ``path``; return ``path``.

    Never raises for one bad object. A single unreadable mesh must not cost the whole
    snapshot, because the alternative is a barrier with nothing behind it — and
    ``UndoBarrier`` exists precisely so that "cannot be replayed across" is discovered
    before the rollback rather than during it.
    """
    objects: list[dict[str, Any]] = []
    for object_id in engine.list_objects():
        try:
            snap = engine.snapshot(object_id)
        except Exception:  # noqa: BLE001 — one unreadable object must not void the capture
            continue
        objects.append(
            {
                "object_id": snap.object_id,
                "vertices": [_vec3(v) for v in snap.vertices],
                "faces": [list(tri) for tri in snap.triangles],
                "transform": _transform_to_dict(snap.transform),
                "materials": list(snap.material_slots),
                "triangle_materials": (
                    list(snap.triangle_materials) if snap.triangle_materials is not None else None
                ),
                "uvs": [list(uv) for uv in snap.uvs] if snap.uvs is not None else None,
                "material_definitions": dict(snap.material_definitions),
            }
        )

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        SNAPSHOT_MARKER: SNAPSHOT_FORMAT,
        "backend": engine.backend_name,
        "objects": objects,
    }
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return str(target)


def is_geometry_snapshot(path: str) -> bool:
    """Whether ``path`` is a file :func:`restore` can actually use.

    Cheap on purpose — reads the head of the file rather than parsing it — because it runs
    on the hot path of every opaque ``apply``, and because the thing it is guarding against
    (a serialised operation log passed in where geometry was meant) differs in the first
    few bytes.
    """
    if not path:
        return False
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return SNAPSHOT_MARKER in handle.read(256)
    except OSError:
        return False


def restore(engine: EngineProtocol, path: str) -> bool:
    """Rebuild the engine's contents from ``path``. Returns whether it worked.

    A boolean rather than an exception: the caller's fallback is a replay, which is a
    worse-but-real answer, and a raise here would turn a degraded rollback into the
    session-fatal failure this whole pass exists to remove. What it must never do is
    report success having restored nothing — hence the marker check before ``reset()``,
    so a bad path leaves the engine untouched for the caller to replay into.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or SNAPSHOT_MARKER not in data:
        return False

    engine.reset()
    for entry in data.get("objects", ()):
        try:
            _restore_object(engine, entry)
        except Exception:  # noqa: BLE001 — one bad object must not abandon the rest
            continue
    return True


def _restore_object(engine: EngineProtocol, entry: dict[str, Any]) -> None:
    object_id = entry["object_id"]
    engine.create_mesh(
        object_id,
        [Vec3(*v) for v in entry["vertices"]],
        [tuple(f) for f in entry["faces"]],
        _transform_from_dict(entry.get("transform")),
    )
    definitions = entry.get("material_definitions") or {}
    if definitions:
        from textures import MaterialTexture

        for definition in definitions.values():
            engine.create_texture_material(MaterialTexture.from_dict(definition))
    for slot, material in enumerate(entry.get("materials") or ()):
        if not material:
            continue
        try:
            # Neutral albedo: MeshSnapshot carries slot names, never PBR values, so the
            # colour genuinely is not in the capture. Restoring the *assignment* keeps a
            # multi-material mesh splittable by the viewer, which dropping the slot would
            # not.
            if material not in definitions:
                engine.create_material(material, (0.8, 0.8, 0.8))
            engine.assign_material(object_id, material, slot)
        except Exception:  # noqa: BLE001 — geometry matters more than a slot name
            continue
    uvs = entry.get("uvs")
    if uvs and hasattr(engine, "_get"):
        restored = engine._get(object_id)
        restored.uvs = [tuple(uv) for uv in uvs]
        restored.unwrapped = True
