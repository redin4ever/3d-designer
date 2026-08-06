"""The composition root — where sixteen modules become one product.

Nothing else in the codebase constructs more than its own dependencies. Rule 5 keeps every
module from reaching into a sibling, which is what made them safe to build in parallel; the
cost is that somebody has to do the wiring, once, in a place allowed to know about all of
them. This is that place.

What it assembles:

    engine  ──> Scene(engine, handlers)  ──> Orchestrator(scene)  ──> MCP registry
                      │                            │
                      └──> ViewerBridge ───────────┘

The handler registry comes from :mod:`app.handlers`, which adapts each operation module's
own calling convention to the one ``scene`` replays through.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from contracts import CheckCadence, EngineProtocol, HandlerRegistry, ToolRole, ToolSpec

from .handlers import MISSING_MODULES, build_handlers

log = logging.getLogger(__name__)

__all__ = ["App", "build_app", "build_handlers", "MISSING_MODULES"]


@dataclass
class App:
    """One live system. Hold this and everything is reachable."""

    engine: EngineProtocol
    scene: Any
    orchestrator: Any
    handlers: HandlerRegistry
    registry: dict[ToolRole, tuple[ToolSpec, ...]] = field(default_factory=dict)
    viewer: Any = None
    backend: str = ""
    missing: tuple[str, ...] = ()

    def describe(self) -> str:
        """What a person needs to know at startup, in the order they need it.

        Deliberately states what is *unavailable* first. A tool that quietly starts with
        half its capabilities missing is worse than one that refuses to start, because the
        agent discovers the gap by failing halfway through a build.
        """
        lines = [f"forge3d — engine: {self.backend}"]
        if self.missing:
            lines.append(f"  UNAVAILABLE: {', '.join(self.missing)} — their tools are absent")
        lines.append(f"  {len(self.handlers)} operations registered")
        for role in ToolRole:
            tools = self.registry.get(role, ())
            if tools:
                lines.append(f"  {role.value:9} {len(tools)} tools: {', '.join(t.name for t in tools)}")
        cadence = getattr(self.scene.document, "check_cadence", None)
        if cadence is not None:
            lines.append(f"  check cadence: {cadence}")
        return "\n".join(lines)


def build_engine(*, prefer_blender: bool = True) -> EngineProtocol:
    """A real Blender-backed engine if one can be had, otherwise the in-memory fake.

    The fallback is deliberate and loud. Everything above the engine is written against
    ``EngineProtocol``, so the system genuinely runs either way — but the fake approximates
    non-planar primitives with their bounding boxes and does not perform real boolean cuts,
    so anything it produces is a smoke test, never an asset. Saying so at startup is the
    difference between a limitation and a lie.
    """
    if prefer_blender:
        try:
            from engine import create_engine

            eng = create_engine()
            log.info("engine: %s", eng.backend_name)
            return eng
        except Exception as exc:  # noqa: BLE001 — falling back is the point
            log.warning(
                "Blender engine unavailable (%s) — falling back to the in-memory fake. "
                "Geometry produced this way is NOT an asset: primitives are bounding-box "
                "approximations and booleans do not cut.",
                exc,
            )
    from testing import FakeEngine

    return FakeEngine()


def build_app(
    *,
    prefer_blender: bool = True,
    include_raw: bool = True,
    scene_id: str = "scene",
    cadence: CheckCadence = CheckCadence.EVERY_GEOMETRY_CHANGE,
    attach_viewer: bool = True,
) -> App:
    """Construct and wire everything. This is the only function that knows the whole shape."""
    engine = build_engine(prefer_blender=prefer_blender)
    handlers = build_handlers(include_raw=include_raw)

    from scene import Scene

    scene = Scene(engine, handlers, scene_id=scene_id)
    scene.document.check_cadence = cadence

    from orchestration import Orchestrator

    orchestrator = Orchestrator(scene, cadence=cadence)

    registry: dict[ToolRole, tuple[ToolSpec, ...]] = {}
    try:
        from mcp_server import build_registry

        registry = build_registry(include_raw=include_raw)
    except Exception as exc:  # noqa: BLE001
        log.error("tool registry unavailable — no agent can call anything: %s", exc)

    viewer = None
    if attach_viewer:
        try:
            from viewer import ViewerBridge

            viewer = ViewerBridge(scene, orchestrator)
            viewer.attach()
        except Exception as exc:  # noqa: BLE001 — the core must survive a broken viewer
            log.warning("live view unavailable, continuing headless: %s", exc)

    return App(
        engine=engine,
        scene=scene,
        orchestrator=orchestrator,
        handlers=handlers,
        registry=registry,
        viewer=viewer,
        backend=engine.backend_name,
        missing=tuple(MISSING_MODULES),
    )
