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
from .model_io import ModelIOMixin
from .modifiers import ModifierOpsMixin
from .raw import RawOpsMixin
from .replacing import MeshReplaceMixin
from .surfacing import SurfacingMixin
from .text import TextOpsMixin

__all__ = ["BlenderEngine", "create_engine"]


class BlenderEngine(
    MeshOpsMixin,
    TextOpsMixin,
    MeshReplaceMixin,
    ModifierOpsMixin,
    SurfacingMixin,
    ModelIOMixin,
    ExportingMixin,
    RawOpsMixin,
):
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


def create_engine() -> EngineProtocol:
    """Composition-root factory (ADR-008). In-process ``bpy``, and nothing else.

    This took a ``prefer_subprocess`` flag until Gate B 2.3, whose ``True`` branch was a bare
    ``NotImplementedError``. Phase 4 established that ``bpy``-as-a-module **does** have
    window access in this build — correcting an early research note — so unwrap, bake and
    glTF export all run in-process and the fallback the flag named was never needed, never
    built, and never called. A stub that looks load-bearing from the outside is worse than
    no stub: it read as a supported deployment mode in ``ARCHITECTURE.md`` for a whole pass.

    What is *not* removed is the capability check itself. :class:`~contracts.EngineUnavailable`
    and the windowed-context reasoning stay, because a machine that genuinely lacks the
    capability should be told so by name rather than by a silent wrong result.

    Nothing outside ``src/engine/`` should ever construct :class:`BlenderEngine` directly —
    this factory is the one seam the rest of the product is allowed to depend on.
    """
    return BlenderEngine()
