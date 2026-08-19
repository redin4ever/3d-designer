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

from .phases import CheckCadence

__all__ = [
    "WIRE_VERSION",
    "ServerMessageType",
    "ClientMessageType",
    "MeshPayload",
    "TransformPayload",
    "RollbackTarget",
    "RedirectPayload",
    "CadencePayload",
    "ServerMessage",
    "ClientMessage",
    "AnnotatePayload",
    "FocusPayload",
    "MAX_ANNOTATION_IMAGE_BYTES",
]

WIRE_VERSION = 1

MAX_ANNOTATION_IMAGE_BYTES = 4_000_000
"""The largest crop an :class:`AnnotatePayload` may carry, as encoded characters.

Declared here rather than in either endpoint because both have to agree, and the failure when
they do not is the ugly kind: ``websockets`` does not error on an over-length frame, it
**closes the connection**. The operator would see the live view drop, with no reason given, at
the exact moment they tried to say something.

Four million leaves comfortable room for the 1024px crop chosen at Q-23 — such a crop of this
renderer's flat-shaded output typically base64-encodes to a few hundred kilobytes — while
staying far enough under a raised transport limit that a large one still arrives.
"""


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
    EXPORT_REPORT = "export_report"
    """Carries the export warning banner (Gate A 6.3). Separate from ``PROBLEMS`` because
    an export banner is about a file that was written, not about the live scene."""

    RESYNC_REQUIRED = "resync_required"
    ERROR = "error"

    FOCUS = "focus"
    """The parts the operator has marked as important, echoed to every watcher. Gate A 10.1
    chose many watchers on one session, and a mark one of them puts up that the others never
    see makes the build look like it is being redirected by nobody."""


class ClientMessageType(StrEnum):
    """Operator controls (Gate A 5.4). The build runs fully autonomously; these exist so
    a human watching can take the wheel without stopping it by default."""

    PAUSE = "pause"
    RESUME = "resume"
    ROLLBACK = "rollback"
    """Payload: :class:`RollbackTarget`."""

    REDIRECT = "redirect"
    """Payload: :class:`RedirectPayload`."""

    REQUEST_FULL_SCENE = "request_full_scene"
    SET_CADENCE = "set_cadence"
    """Payload: :class:`CadencePayload`. The settings control asked for at Gate A 3.1."""

    SELECT = "select"

    ANNOTATE = "annotate"
    """Payload: :class:`AnnotatePayload`. What the operator is pointing at, what they said
    about it, and optionally a picture of it."""

    SET_FOCUS = "set_focus"
    """Payload: :class:`FocusPayload`. The complete set of parts the operator has marked as
    important — declarative, so an empty set is how you clear."""


@dataclass(frozen=True, slots=True)
class AnnotatePayload:
    """The operator pointing at part of the scene, with optional words and an optional crop.

    Any one of the three is a complete annotation on its own: pointing with nothing to say is
    a whole gesture (Q-04), and typing with nothing selected is the redirect composer that
    already existed. What is refused is all three being empty.
    """

    object_ids: tuple[str, ...] = ()
    text: str = ""
    image: str = ""
    """A ``data:`` URL, produced by ``canvas.toDataURL`` in the browser (A-012)."""

    def __post_init__(self) -> None:
        if not self.object_ids and not self.text.strip() and not self.image:
            raise ValueError(
                "an annotation with nothing in it — no object, no text, no image — would "
                "travel the whole way to the agent and do nothing"
            )
        if self.image:
            if not self.image.startswith("data:"):
                # A remote URL here would have the server fetching an address the browser
                # chose. That is not a capability this feature asked for, and ADR-009's
                # trust boundary is this machine, not whatever the page decided to name.
                raise ValueError(
                    f"an annotation image must be a data: URL, not {self.image[:32]!r}"
                )
            if len(self.image) > MAX_ANNOTATION_IMAGE_BYTES:
                raise ValueError(
                    f"annotation image is {len(self.image)} bytes, over the "
                    f"{MAX_ANNOTATION_IMAGE_BYTES} limit — send a smaller crop; a frame past "
                    "the transport's limit closes the connection instead of erroring"
                )


@dataclass(frozen=True, slots=True)
class FocusPayload:
    """The complete set of parts the operator has marked as important.

    Declarative, never a delta: the whole set arrives each time, so an empty one is how you
    clear (Q-11). A delta protocol needs a separate clear message, and the two drift apart the
    first time one is dropped — which for a standing instruction means the agent going on
    being told something the operator has already taken back.
    """

    object_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.object_ids)) != len(self.object_ids):
            # Focus is re-attached to every report (A-013), so a duplicate is not a one-off
            # oddity — it tells the agent the same object matters twice, every turn, for the
            # rest of the session.
            raise ValueError("focus names the same object twice")


@dataclass(frozen=True, slots=True)
class RollbackTarget:
    """Where to roll back to. Exactly one of the two.

    Typed rather than a free dict because ``frontend`` and ``viewer`` are built in
    parallel against this file alone. A disagreement about whether the key is ``steps``
    or ``count`` surfaces only at live WebSocket runtime, which is the worst place to
    find it.
    """

    steps: int | None = None
    checkpoint: str | None = None

    def __post_init__(self) -> None:
        if (self.steps is None) == (self.checkpoint is None):
            raise ValueError("rollback takes exactly one of steps or checkpoint")
        if self.steps is not None and self.steps < 1:
            raise ValueError(f"rollback steps must be >= 1, got {self.steps}")


@dataclass(frozen=True, slots=True)
class RedirectPayload:
    """A free-text instruction typed by the operator mid-run.

    It reaches the agent by riding out on the next tool response, in
    ``ActionReport.operator_notes`` — MCP is call/response, so a server cannot push into
    a connected agent's context uninvited.
    """

    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a redirect with no text would be silently dropped")


@dataclass(frozen=True, slots=True)
class CadencePayload:
    cadence: CheckCadence


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
    materials: tuple[str, ...] = ()
    """All material slots, not one. A mesh with several materials cannot be rendered
    faithfully from a single name, and silently keeping the first is a rendering bug that
    looks like a modelling bug."""

    groups: tuple[tuple[int, int, int], ...] = ()
    """``(start, count, material_index)`` draw ranges over ``indices``, one per material
    run. Empty means the whole mesh uses ``materials[0]``."""

    triangle_count: int = 0
    material_definitions: dict[str, dict] = field(default_factory=dict)


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
    """Monotonic, assigned by exactly one counter in ``viewer``. Never set by a caller.

    Client rules, both required:

    - **Gap** (``seq > last_applied + 1``) → request a full resync. A silently stale
      viewport is worse than a slow one.
    - **Duplicate or out-of-order** (``seq <= last_applied``) → ignore. Retries happen,
      and a client that applies mesh updates additively would otherwise double-apply one.
    """

    meshes: tuple[MeshPayload, ...] = ()
    transforms: tuple[TransformPayload, ...] = ()
    object_ids: tuple[str, ...] = ()
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClientMessage:
    type: ClientMessageType
    data: dict[str, Any] = field(default_factory=dict)
