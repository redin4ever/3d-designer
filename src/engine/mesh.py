"""Stub ``MeshOps`` — mesh creation, editing and inspection against bpy.

Every method raises. This file fixes the shape :class:`~engine.session.BlenderEngine`
inherits so the conformance suite (``src/engine/conformance.py``) fails on
``NotImplementedError``, never ``ImportError`` (Rule 4 RED). The behavioural contract each
method must satisfy is documented on ``MeshOps`` in ``src/contracts/engine.py`` and enforced
by the conformance checks — this file carries no logic of its own to keep it that way.
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, MeshSnapshot, Transform, Vec3

__all__ = ["MeshOpsMixin"]


class MeshOpsMixin:
    """``MeshOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def create_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
        transform: Transform | None = None,
    ) -> str:
        raise NotImplementedError("engine.create_mesh: not implemented")

    def create_primitive(
        self, object_id: str, kind: str, size: Vec3, transform: Transform | None = None
    ) -> str:
        raise NotImplementedError("engine.create_primitive: not implemented")

    def duplicate(self, object_id: str, new_id: str, transform: Transform | None = None) -> str:
        raise NotImplementedError("engine.duplicate: not implemented")

    def delete(self, object_id: str) -> None:
        raise NotImplementedError("engine.delete: not implemented")

    def set_transform(self, object_id: str, transform: Transform) -> None:
        raise NotImplementedError("engine.set_transform: not implemented")

    def apply_transform(
        self, object_id: str, *, location: bool, rotation: bool, scale: bool
    ) -> None:
        raise NotImplementedError("engine.apply_transform: not implemented")

    def join(self, target_id: str, source_ids: Sequence[str]) -> str:
        raise NotImplementedError("engine.join: not implemented")

    def separate_loose(self, object_id: str) -> list[str]:
        raise NotImplementedError("engine.separate_loose: not implemented")

    def snapshot(self, object_id: str) -> MeshSnapshot:
        raise NotImplementedError("engine.snapshot: not implemented")

    def list_objects(self) -> list[str]:
        raise NotImplementedError("engine.list_objects: not implemented")

    def exists(self, object_id: str) -> bool:
        raise NotImplementedError("engine.exists: not implemented")

    def world_bounds(self, object_id: str) -> AABB:
        raise NotImplementedError("engine.world_bounds: not implemented")
