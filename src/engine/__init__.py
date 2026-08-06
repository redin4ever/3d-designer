"""``engine`` — the only module in this repository permitted to ``import bpy``.

Implements ``contracts.EngineProtocol`` against Blender 5.2's data API (ADR-001). Every
other module is written against the Protocol and is handed either this or
``testing.FakeEngine`` at the composition root (ADR-008) — see ``src/engine/README.md``.

Barrel: re-exports only, no logic (Rule 2).
"""

from __future__ import annotations

from .session import BlenderEngine, create_engine

__all__ = ["BlenderEngine", "create_engine"]
