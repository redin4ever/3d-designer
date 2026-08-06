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
from .errors import (
    ProposalConflict,
    RuleError,
    RunPaused,
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
    RepairOutcome,
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
from .geometry import (
    EPSILON,
    EPSILON_SAFE_RADIUS,
    AABB,
    MeshSnapshot,
    Quat,
    Transform,
    Vec3,
    WORLD_UP,
    epsilon_at,
)
from .measurement import (
    DEFAULT_SEVERITY,
    AcceptanceQuery,
    AcceptanceResult,
    Comparison,
    Defect,
    DefectClass,
    Measurement,
    MeasurementReport,
    MetricKind,
    Severity,
    reconcile_tolerance,
)
from .operations import (
    DETAIL_THRESHOLD,
    ActionReport,
    ExportReport,
    HandlerRegistry,
    JoineryIntent,
    MutatingHandler,
    Operation,
    OperationHandler,
    OperationResult,
    OperationStatus,
    Proposal,
    ReadHandler,
    ToolError,
    ToolRole,
    ToolSpec,
)
from .phases import (
    ALWAYS_LEGAL_ROLES,
    PHASE_ORDER,
    PHASE_ROLES,
    CheckCadence,
    Conflict,
    LockContention,
    Phase,
    PhasePromotion,
    PhaseViolation,
    RunState,
    WriteLease,
    WriteLockManager,
    roles_for_phase,
)
from .scene_doc import (
    MIN_READABLE_SCHEMA,
    SCHEMA_VERSION,
    ChangeKind,
    Checkpoint,
    SceneChangeEvent,
    SceneDocument,
    ScenePort,
    UndoBarrier,
)
from .wire import (
    WIRE_VERSION,
    CadencePayload,
    ClientMessage,
    ClientMessageType,
    MeshPayload,
    RedirectPayload,
    RollbackTarget,
    ServerMessage,
    ServerMessageType,
    TransformPayload,
)

__all__ = [
    # errors — the one shape every named failure takes (ADR-013, Gate B 5.4)
    "RuleError", "RunPaused", "ProposalConflict",
    # geometry
    "EPSILON", "EPSILON_SAFE_RADIUS", "epsilon_at",
    "AABB", "MeshSnapshot", "Quat", "Transform", "Vec3", "WORLD_UP",
    # engine
    "EngineProtocol", "EngineError", "EngineUnavailable", "RepairOutcome",
    "MeshOps", "ModifierOps", "MaterialOps", "UVBakeOps", "ExportOps", "RawOps",
    # measurement
    "MetricKind", "DefectClass", "Severity", "DEFAULT_SEVERITY", "Comparison",
    "Measurement", "Defect", "MeasurementReport", "AcceptanceQuery", "AcceptanceResult",
    "reconcile_tolerance",
    # constraints
    "ConstraintKind", "AnchorKind", "Anchor", "Constraint", "ConstraintSet",
    "Placement", "ConstraintError", "CYCLE_RULE",
    # operations
    "OperationStatus", "JoineryIntent", "Operation", "OperationResult",
    "OperationHandler", "HandlerRegistry", "Proposal",
    "ActionReport", "ExportReport", "ToolRole", "ToolSpec",
    "MutatingHandler", "ReadHandler", "ToolError", "DETAIL_THRESHOLD",
    # scene document
    "SceneDocument", "ScenePort", "Checkpoint", "UndoBarrier", "ChangeKind",
    "SceneChangeEvent", "SCHEMA_VERSION", "MIN_READABLE_SCHEMA",
    # phases
    "Phase", "PHASE_ORDER", "PHASE_ROLES", "ALWAYS_LEGAL_ROLES", "roles_for_phase",
    "CheckCadence", "RunState", "WriteLease",
    "WriteLockManager", "LockContention", "PhaseViolation", "Conflict", "PhasePromotion",
    # export
    "UpAxis", "Handedness", "AssetClass", "ExportProfile", "PROFILES",
    "DEFAULT_PROFILE", "profile_for",
    # wire
    "WIRE_VERSION", "ServerMessageType", "ClientMessageType", "MeshPayload",
    "TransformPayload", "ServerMessage", "ClientMessage",
    "RollbackTarget", "RedirectPayload", "CadencePayload",
]
