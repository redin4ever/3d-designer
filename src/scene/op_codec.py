"""``Operation`` to JSON and back, including the nested dataclasses (ADR-015, Gate B 1.2).

Schema version 1 wrote nine of ``Operation``'s fields and dropped five: ``placements``
(the ``ConstraintSet``), ``joinery``, ``acceptance``, ``asset_class`` and ``proposal_id``.
ADR-002 chose a parametric document for one stated payoff — move the stair, and the
railing constrained to its outer edge follows — and that is exactly what did not survive a
reload. The geometry came back; the reason for it did not.

Split out of ``persistence.py`` because it is a distinct data shape rather than a distinct
step: ``save``/``load`` decide the file's *envelope* (version, head, checkpoints,
barriers), this decides how one operation and everything hanging off it is written.

Encoding rules, all three chosen because the alternative is ambiguous on the way back:

- A ``Vec3`` is a 3-element JSON array. ``Constraint.value`` is ``float | Vec3 | None``,
  so the decoder needs to tell a scalar from a point without a type tag; a number and an
  array cannot be confused, and a dict-shaped point could be.
- Every ``StrEnum`` is written as its value and reconstructed through the enum, so a value
  this build does not know raises on load rather than lying as a plain string that
  compares unequal to every member.
- Absent, empty and ``None`` are distinct. ``asset_class`` genuinely has no value for most
  operations, and defaulting it to a class would make the polygon budget check answer a
  question nobody asked.
"""

from __future__ import annotations

from typing import Any

from contracts import (
    AcceptanceQuery,
    Anchor,
    AnchorKind,
    AssetClass,
    Comparison,
    Constraint,
    ConstraintKind,
    ConstraintSet,
    DefectClass,
    JoineryIntent,
    MetricKind,
    Operation,
    OperationStatus,
    Vec3,
)

__all__ = ["operation_to_dict", "operation_from_dict", "V1_DROPPED_FIELDS"]

V1_DROPPED_FIELDS = ("placements", "joinery", "acceptance", "asset_class", "proposal_id")
"""What a schema-version-1 file never stored. Named here, once, so the load warning can
list them without a second hand-maintained copy drifting away from this one."""


# ------------------------------------------------------------------------ primitives

def _vec3_to(v: Vec3 | None) -> list[float] | None:
    return None if v is None else [v.x, v.y, v.z]


def _vec3_from(data: Any) -> Vec3 | None:
    return None if data is None else Vec3(*(float(c) for c in data))


def _value_to(value: float | Vec3 | None) -> Any:
    return _vec3_to(value) if isinstance(value, Vec3) else value


def _value_from(data: Any) -> float | Vec3 | None:
    if data is None:
        return None
    return _vec3_from(data) if isinstance(data, (list, tuple)) else float(data)


# ------------------------------------------------------------------------ constraints

def _anchor_to(a: Anchor) -> dict[str, Any]:
    return {"kind": str(a.kind), "object_id": a.object_id, "feature": a.feature, "index": a.index}


def _anchor_from(data: dict[str, Any]) -> Anchor:
    return Anchor(
        kind=AnchorKind(data["kind"]),
        object_id=data.get("object_id", ""),
        feature=data.get("feature", ""),
        index=data.get("index"),
    )


def _constraint_to(c: Constraint) -> dict[str, Any]:
    return {
        "kind": str(c.kind),
        "target": _anchor_to(c.target),
        "value": _value_to(c.value),
        "axis": _vec3_to(c.axis),
        "tolerance": c.tolerance,
        "hard": c.hard,
        "params": c.params,
    }


def _constraint_from(data: dict[str, Any]) -> Constraint:
    return Constraint(
        kind=ConstraintKind(data["kind"]),
        target=_anchor_from(data["target"]),
        value=_value_from(data.get("value")),
        axis=_vec3_from(data.get("axis")),
        tolerance=data.get("tolerance", 1e-4),
        hard=data.get("hard", True),
        params=data.get("params", {}),
    )


def _constraint_set_to(cs: ConstraintSet) -> dict[str, Any]:
    return {
        "object_id": cs.object_id,
        "constraints": [_constraint_to(c) for c in cs.constraints],
        "raw_position": _vec3_to(cs.raw_position),
    }


def _constraint_set_from(data: dict[str, Any]) -> ConstraintSet:
    return ConstraintSet(
        object_id=data["object_id"],
        constraints=tuple(_constraint_from(c) for c in data.get("constraints", ())),
        raw_position=_vec3_from(data.get("raw_position")),
    )


# ------------------------------------------------------------- joinery and acceptance

def _joinery_to(j: JoineryIntent) -> dict[str, Any]:
    return {
        "object_id": j.object_id,
        "into_object_id": j.into_object_id,
        "depth": j.depth,
        "tolerance": j.tolerance,
        "reason": j.reason,
        "axis": j.axis,
    }


def _joinery_from(data: dict[str, Any]) -> JoineryIntent:
    return JoineryIntent(
        object_id=data["object_id"],
        into_object_id=data["into_object_id"],
        depth=data["depth"],
        tolerance=data.get("tolerance", 1e-3),
        reason=data.get("reason", ""),
        axis=data.get("axis", ""),
    )


def _acceptance_to(q: AcceptanceQuery) -> dict[str, Any]:
    return {
        "query_id": q.query_id,
        "description": q.description,
        "metric": None if q.metric is None else str(q.metric),
        "forbidden_defects": [str(d) for d in q.forbidden_defects],
        "subject": q.subject,
        "expected": q.expected,
        "tolerance": q.tolerance,
        "comparison": str(q.comparison),
        "params": q.params,
    }


def _acceptance_from(data: dict[str, Any]) -> AcceptanceQuery:
    metric = data.get("metric")
    return AcceptanceQuery(
        query_id=data["query_id"],
        description=data.get("description", ""),
        metric=None if metric is None else MetricKind(metric),
        forbidden_defects=tuple(DefectClass(d) for d in data.get("forbidden_defects", ())),
        subject=data.get("subject", ""),
        expected=data.get("expected"),
        tolerance=data.get("tolerance", 1e-4),
        comparison=Comparison(data.get("comparison", "none")),
        params=data.get("params", {}),
    )


# -------------------------------------------------------------------------- operation

def operation_to_dict(op: Operation) -> dict[str, Any]:
    """Every field of ``Operation``, with nothing left behind."""
    return {
        "op_id": op.op_id,
        "kind": op.kind,
        "params": op.params,
        "placements": [_constraint_set_to(cs) for cs in op.placements],
        "joinery": [_joinery_to(j) for j in op.joinery],
        "acceptance": [_acceptance_to(q) for q in op.acceptance],
        "phase": op.phase,
        "author": op.author,
        "target_objects": list(op.target_objects),
        "asset_class": None if op.asset_class is None else str(op.asset_class),
        "proposal_id": op.proposal_id,
        "opaque": op.opaque,
        "produced_objects": list(op.produced_objects),
        "status": str(op.status),
    }


def operation_from_dict(data: dict[str, Any]) -> Operation:
    """The inverse. Every ``get`` default matches ``Operation``'s own field default, so a
    version-1 file — which simply has no key for the five fields it never stored — decodes
    to exactly the operation it described, rather than to one with invented intent."""
    asset_class = data.get("asset_class")
    return Operation(
        op_id=data["op_id"],
        kind=data["kind"],
        params=data.get("params", {}),
        placements=tuple(_constraint_set_from(c) for c in data.get("placements", ())),
        joinery=tuple(_joinery_from(j) for j in data.get("joinery", ())),
        acceptance=tuple(_acceptance_from(q) for q in data.get("acceptance", ())),
        phase=data.get("phase", "blockout"),
        author=data.get("author", ""),
        target_objects=tuple(data.get("target_objects", ())),
        asset_class=None if asset_class is None else AssetClass(asset_class),
        proposal_id=data.get("proposal_id", ""),
        opaque=data.get("opaque", False),
        produced_objects=tuple(data.get("produced_objects", ())),
        status=OperationStatus(data.get("status", "pending")),
    )
