"""The WebSocket wire protocol, shared by ``src/viewer/`` and ``frontend/``.

Freezing it here is what lets the Puppeteer suite drive the browser against recorded
fixtures with no Python and no Blender running (ADR-008), and it is why ``frontend`` can
be built in parallel with everything else.

There is no production-ready incremental glTF or USD streaming format, so this is a
custom diff protocol with a full-reload fallback. The fallback is not a nicety: any
topology change or opaque edit forces it, and it is the correctness path the fast path
degrades to (ADR-011).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "WIRE_VERSION",
    "ServerMessageType",
    "ClientMessageType",
    "MeshPayload",
    "TransformPayload",
    "ServerMessage",
    "ClientMessage",
]

WIRE_VERSION = 1


class ServerMessageType(StrEnum):
    HELLO = "hello"
    """Sent once on connect: wire version, scene id, unit scale, current phase."""

    FULL_SCENE = "full_scene"
    """Every object. Sent on connect and on any resync."""

    MESH_UPSERT = "mesh_upsert"
    """New or topology-changed objects, with buffers."""

    TRANSFORM_UPDATE = "transform_update"
    """The cheap path — node transforms only, no buffers. The common case."""

    OBJECTS_REMOVED = "objects_removed"
    HIGHLIGHT = "highlight"
    """What just changed, so the operator can find it without hunting (Gate A 5.3)."""

    LOG = "log"
    PHASE = "phase"
    RUN_STATE = "run_state"
    PROBLEMS = "problems"
    CONFLICT = "conflict"
    RESYNC_REQUIRED = "resync_required"
    ERROR = "error"


class ClientMessageType(StrEnum):
    """Operator controls (Gate A 5.4). The build runs fully autonomously; these exist so
    a human watching can take the wheel without stopping it by default."""

    PAUSE = "pause"
    RESUME = "resume"
    ROLLBACK = "rollback"
    """``{"steps": N}`` or ``{"checkpoint": "name"}``."""

    REDIRECT = "redirect"
    """``{"text": "..."}`` — free-text instruction injected into the running agent."""

    REQUEST_FULL_SCENE = "request_full_scene"
    SET_CADENCE = "set_cadence"
    """The settings control the user explicitly asked for at Gate A 3.1."""

    SELECT = "select"


@dataclass(frozen=True, slots=True)
class MeshPayload:
    """Flat typed-array-friendly buffers.

    Deliberately flat lists of floats/ints rather than nested objects: these map straight
    onto ``BufferGeometry`` attributes in the browser with no per-vertex object churn,
    which is what keeps a thousands-of-objects scene responsive.
    """

    object_id: str
    positions: list[float]
    indices: list[int]
    normals: list[float] | None = None
    uvs: list[float] | None = None
    material: str = ""
    triangle_count: int = 0


@dataclass(frozen=True, slots=True)
class TransformPayload:
    object_id: str
    position: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]
    """x, y, z, w — three.js order, not the w-first order used internally. Converted once,
    here at the boundary."""

    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class ServerMessage:
    type: ServerMessageType
    seq: int = 0
    """Monotonic. A client that sees a gap requests a full resync rather than rendering a
    scene it cannot prove is current — a silently stale viewport is worse than a slow one."""

    meshes: tuple[MeshPayload, ...] = ()
    transforms: tuple[TransformPayload, ...] = ()
    object_ids: tuple[str, ...] = ()
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClientMessage:
    type: ClientMessageType
    data: dict[str, Any] = field(default_factory=dict)
