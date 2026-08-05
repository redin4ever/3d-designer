"""Conformance checks for session lifecycle — ``reset()`` and ``backend_name``.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/session.py``.
``check_backend_name_identifies_bpy`` is Blender-only — see ``conformance.py``'s module
docstring for why ``FakeEngine`` is exempt.
"""

from __future__ import annotations

from contracts import EngineProtocol

__all__ = [
    "check_reset_leaves_zero_objects",
    "check_backend_name_identifies_bpy",
    "check_reset_clears_the_live_bpy_scene",
]


def check_reset_leaves_zero_objects(engine: EngineProtocol) -> None:
    """A fresh bpy scene is not empty — it holds Blender's default cube, camera and light.
    ``reset()`` must clear all scene content, not just objects this session tracked itself,
    or every "the scene starts empty" assumption in the product breaks silently."""
    engine.reset()
    assert engine.list_objects() == []


def check_backend_name_identifies_bpy(engine: EngineProtocol) -> None:
    """A scene document that cannot say which engine produced a result cannot explain a
    discrepancy after a Blender version bump (ADR-001) — was this object made by 5.2 or by
    whatever replaces it?"""
    assert engine.backend_name.startswith("bpy-"), (
        f"backend_name {engine.backend_name!r} does not start with 'bpy-'"
    )


def check_reset_clears_the_live_bpy_scene(engine: EngineProtocol) -> None:
    """Blender-only, added in response to a conformance audit: ``blender_test.py``'s
    fixture calls ``reset()`` before every test body, so no other check ever observes a
    ``BlenderEngine`` that has NOT already been reset. If ``list_objects()`` reads from a
    private Python-side ledger (as ``FakeEngine``'s does), ``reset()`` could be
    ``self._tracked.clear()`` and never touch the live Blender scene at all — every other
    check would still pass while the default cube sits there forever. This reads
    ``bpy.data.objects`` DIRECTLY, bypassing ``engine.list_objects()`` entirely, so a
    self-consistent wrapper disconnected from real bpy state cannot fake its way past it.
    A raw probe object is linked directly via ``bpy.data`` first (rather than relying on
    Blender's default cube alone) so this check holds regardless of what an earlier test in
    the same session already did to the scene."""
    import bpy  # local: this module must stay importable with no bpy installed

    mesh = bpy.data.meshes.new("conformance_probe")
    probe = bpy.data.objects.new("conformance_probe", mesh)
    bpy.context.scene.collection.objects.link(probe)
    assert len(bpy.data.objects) >= 1

    engine.reset()

    assert list(bpy.data.objects) == []
