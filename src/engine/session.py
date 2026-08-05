"""``BlenderEngine`` — bpy lifecycle, session identity and scene reset.

**This is the only module in the repository permitted to ``import bpy``** (see
``src/engine/README.md``). ``BlenderEngine`` composes the five ``Ops`` mixins into the
concrete :class:`contracts.EngineProtocol` implementation; this file owns only what does not
belong to any single ``Ops`` group: construction, ``backend_name``, and ``reset()``.

``reset()`` is the sharpest edge in this file. A fresh ``bpy`` scene is not empty — it holds
Blender's default cube, camera and light — and ``reset()`` must clear all of it, not just
objects this session created. See ``conformance.check_reset_leaves_zero_objects``: a naive
implementation that tracks "objects I made" and deletes only those leaves the default cube
behind, and every downstream "the scene starts empty" assumption breaks silently for it.

Every method below raises. No bpy import happens yet, deliberately: this file only fixes the
shape the implementer inherits (Rule 4 RED) so the conformance suite fails on
``NotImplementedError``, never ``ImportError``, on a machine with no Blender at all.
"""

from __future__ import annotations

from contracts import EngineProtocol

from .exporting import ExportingMixin
from .mesh import MeshOpsMixin
from .modifiers import ModifierOpsMixin
from .raw import RawOpsMixin
from .surfacing import SurfacingMixin

__all__ = ["BlenderEngine", "create_engine"]


class BlenderEngine(MeshOpsMixin, ModifierOpsMixin, SurfacingMixin, ExportingMixin, RawOpsMixin):
    """The real ``EngineProtocol`` implementation, against Blender 5.2's data API.

    Construction alone must not raise ``NotImplementedError`` — a caller needs to be able to
    hold an (unusable, pre-implementation) instance and pass it around, e.g. to
    ``isinstance(engine, EngineProtocol)`` checks and to fixtures that call ``reset()``
    themselves and expect ``NotImplementedError`` from that call, not from construction.
    """

    def __init__(self) -> None:
        pass

    @property
    def backend_name(self) -> str:
        """e.g. ``"bpy-5.2.0"``. Must start with ``"bpy-"`` — see
        ``conformance.check_backend_name_identifies_bpy``. Read ``bpy.app.version_string``
        (ADR-001 verified this is live: ``'5.2.0 LTS'``) rather than hardcoding a version."""
        import bpy

        return f"bpy-{bpy.app.version_string}"

    def reset(self) -> None:
        """Clear every scene datablock, not just objects this session tracked.

        Objects first (``do_unlink=True`` detaches them from every collection/scene), then
        the datablock types that can accumulate across a session — meshes, materials,
        cameras, lights, images — regardless of who created them (the default cube/camera/
        light included, and any raw ``bpy.data`` object a caller linked directly, per
        ``conformance_session.check_reset_clears_the_live_bpy_scene``). Each removal is
        best-effort: one datablock bpy refuses to drop (e.g. still fake-user-protected) must
        not abort clearing the rest.
        """
        import bpy

        for obj in list(bpy.data.objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except RuntimeError:
                pass

        for collection in (
            bpy.data.meshes,
            bpy.data.materials,
            bpy.data.cameras,
            bpy.data.lights,
            bpy.data.images,
            bpy.data.node_groups,
            bpy.data.curves,
        ):
            for block in list(collection):
                try:
                    collection.remove(block)
                except RuntimeError:
                    pass


def create_engine(prefer_subprocess: bool = False) -> EngineProtocol:
    """Composition-root factory (ADR-008).

    ``prefer_subprocess=False`` (the default) is in-process ``bpy`` — the normal path, and
    the only one exercised by ``src/engine/blender_test.py``. ``prefer_subprocess=True`` is
    the documented fallback for capabilities in-process ``bpy`` structurally cannot provide,
    shelling out to the real ``blender.exe``. No test in this suite exercises that path, and
    it is not implemented here — raising rather than silently falling back to the in-process
    engine, which would hide the exact capability gap this flag exists to name.
    Nothing outside ``src/engine/`` should ever construct :class:`BlenderEngine` directly —
    this factory is the one seam the rest of the product is allowed to depend on.
    """
    if prefer_subprocess:
        raise NotImplementedError(
            "engine.create_engine: prefer_subprocess=True (blender.exe subprocess fallback) "
            "is not implemented — no check in this suite exercises it"
        )
    return BlenderEngine()
