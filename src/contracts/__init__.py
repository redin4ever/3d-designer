"""Frozen shared surface. Owned by the main agent alone — no module agent edits this.

Every module compiles against these types, which is what makes parallel construction safe
and what turns ``dependsOn`` into an integration order rather than a build queue.

A module needing a change here does **not** edit it. It appends to
``.pipeline/contract-requests.json`` and adapts locally; the main agent reconciles between
rounds (Rule 5).

This file is a barrel: re-exports only, no logic.
"""

from .constraints import (
    CYCLE_RULE,
    Anchor,
    AnchorKind,
    Constraint,
    ConstraintError,
    ConstraintKind,
    ConstraintSet,
    Placement,
)
from .engine import (
    EngineError,
    EngineProtocol,
    EngineUnavailable,
    ExportOps,
    MaterialOps,
    MeshOps,
    ModifierOps,
    RawOps,
    UVBakeOps,
)
from .export_profiles import (
    DEFAULT_PROFILE,
    PROFILES,
    AssetClass,
    ExportProfile,
    Handedness,
    UpAxis,
    profile_for,
)
from .geometry import EPSILON, AABB, MeshSnapshot, Quat, Transform, Vec3, WORLD_UP
from .measurement import (
    AcceptanceQuery,
    AcceptanceResult,
    Defect,
    DefectClass,
    Measurement,
    MeasurementReport,
    MetricKind,
    Severity,
)
from .operations import (
    ActionReport,
    JoineryIntent,
    Operation,
    OperationResult,
    OperationStatus,
    ToolError,
    ToolRole,
    ToolSpec,
)
from .phases import (
    PHASE_ORDER,
    CheckCadence,
    Conflict,
    Phase,
    PhasePromotion,
    Proposal,
    RunState,
    WriteLease,
)
from .scene_doc import (
    SCHEMA_VERSION,
    ChangeKind,
    Checkpoint,
    SceneChangeEvent,
    SceneDocument,
    UndoBarrier,
)
from .wire import (
    WIRE_VERSION,
    ClientMessage,
    ClientMessageType,
    MeshPayload,
    ServerMessage,
    ServerMessageType,
    TransformPayload,
)

__all__ = [
    # geometry
    "EPSILON", "AABB", "MeshSnapshot", "Quat", "Transform", "Vec3", "WORLD_UP",
    # engine
    "EngineProtocol", "EngineError", "EngineUnavailable",
    "MeshOps", "ModifierOps", "MaterialOps", "UVBakeOps", "ExportOps", "RawOps",
    # measurement
    "MetricKind", "DefectClass", "Severity", "Measurement", "Defect",
    "MeasurementReport", "AcceptanceQuery", "AcceptanceResult",
    # constraints
    "ConstraintKind", "AnchorKind", "Anchor", "Constraint", "ConstraintSet",
    "Placement", "ConstraintError", "CYCLE_RULE",
    # operations
    "OperationStatus", "JoineryIntent", "Operation", "OperationResult",
    "ActionReport", "ToolRole", "ToolSpec", "ToolError",
    # scene document
    "SceneDocument", "Checkpoint", "UndoBarrier", "ChangeKind",
    "SceneChangeEvent", "SCHEMA_VERSION",
    # phases
    "Phase", "PHASE_ORDER", "CheckCadence", "RunState", "WriteLease",
    "Proposal", "Conflict", "PhasePromotion",
    # export
    "UpAxis", "Handedness", "AssetClass", "ExportProfile", "PROFILES",
    "DEFAULT_PROFILE", "profile_for",
    # wire
    "WIRE_VERSION", "ServerMessageType", "ClientMessageType", "MeshPayload",
    "TransformPayload", "ServerMessage", "ClientMessage",
]
