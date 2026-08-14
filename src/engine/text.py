"""Portable text-mesh creation for the Blender backend."""

from __future__ import annotations

from contracts import Transform

__all__ = ["TextOpsMixin"]


class TextOpsMixin:
    def create_text(
        self,
        object_id: str,
        text: str,
        height: float,
        depth: float,
        transform: Transform | None = None,
    ) -> str:
        raise NotImplementedError("engine.create_text: not implemented")
