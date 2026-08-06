"""Adapters that make every operation module speak one calling convention.

``scene`` replays a log by looking each ``Operation.kind`` up in a ``HandlerRegistry`` and
calling ``handler(engine, op) -> OperationResult``. Only ``ops`` was written to that shape.
``gaps``, ``align``, ``detail`` and ``uv`` expose ordinary functions —
``fn(engine, object_id, **kwargs)`` returning their own result types — which is the right
shape for a person calling them directly and the wrong shape for replay.

Bridging the two is composition-root work by definition: it needs to know about every
operation module at once, and Rule 5 says no module may reach into a sibling. Without this
file the registry stays empty, every agent tool call resolves to nothing, and the sixteen
green modules are sixteen libraries rather than a product.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from contracts import EngineProtocol, HandlerRegistry, Operation, OperationResult

from contracts import Quat, Transform, Vec3

log = logging.getLogger(__name__)

__all__ = ["build_handlers", "adapt", "coerce_params", "MISSING_MODULES"]


def _is_vec3_schema(s: Any) -> bool:
    return (
        isinstance(s, dict)
        and s.get("type") == "array"
        and s.get("minItems") == 3
        and s.get("maxItems") == 3
        and isinstance(s.get("items"), dict)
        and s["items"].get("type") == "number"
    )


def _is_path_schema(s: Any) -> bool:
    return isinstance(s, dict) and s.get("type") == "array" and _is_vec3_schema(s.get("items"))


def _is_transform_schema(s: Any) -> bool:
    """A placement: an object whose properties are the fields of ``contracts.Transform``.

    Recognised structurally within the *schema*, never within the value — same rule as the
    vec3 case, and for the same reason. Requiring at least one of the three fields, rather
    than an exact match, keeps a schema that declares only ``translation`` working.
    """
    if not isinstance(s, dict) or s.get("type") != "object":
        return False
    props = s.get("properties")
    if not isinstance(props, dict) or not props:
        return False
    return set(props) <= {"translation", "rotation", "scale"} and bool(
        {"translation", "rotation", "scale"} & set(props)
    )


def _coercion_map(input_schema: dict) -> dict[str, str]:
    """Which parameters of one tool are points, and which are polylines.

    Driven by the tool's own declared schema rather than by the shape of the value. A
    structural guess — "a list of three numbers is a point" — would silently convert
    ``add_lod_chain``'s ``ratios=[0.5, 0.25, 0.1]`` into a coordinate. The schema pins a
    vec3 at exactly three items while ``ratios`` is unbounded, so it can tell them apart
    and a guess cannot.
    """
    out: dict[str, str] = {}
    for name, spec in (input_schema or {}).get("properties", {}).items():
        if _is_vec3_schema(spec):
            out[name] = "vec3"
        elif _is_path_schema(spec):
            out[name] = "path"
        elif _is_transform_schema(spec):
            out[name] = "transform"
    return out


def coerce_params(params: dict[str, Any], coercions: dict[str, str]) -> dict[str, Any]:
    """Turn JSON-over-the-wire values into the domain types the operations expect.

    Everything an agent sends arrives as JSON: a point is ``[x, y, z]``, never a ``Vec3``.
    The operation modules deliberately work in ``Vec3`` internally and documented that
    converting at the boundary belongs to whoever owns the boundary. This is that
    boundary. Without it every operation taking a point raises ``AttributeError: 'list'
    object has no attribute 'x'`` the first time a real agent calls it — while every
    module's own suite stays green, because those tests construct ``Vec3`` in Python.
    """
    out = dict(params)
    for name, kind in coercions.items():
        value = out.get(name)
        if value is None:
            continue
        try:
            if kind == "vec3" and not isinstance(value, Vec3):
                out[name] = Vec3(*(float(c) for c in value))
            elif kind == "path":
                out[name] = [p if isinstance(p, Vec3) else Vec3(*(float(c) for c in p)) for p in value]
            elif kind == "transform" and not isinstance(value, Transform):
                # Every field optional and defaulted, so `{"translation": [...]}` is a
                # complete placement. Rotation is [w, x, y, z], matching the schema and
                # `contracts.Quat`'s own field order — the other convention would silently
                # yaw everything an agent placed.
                out[name] = Transform(
                    translation=Vec3(*(float(c) for c in value.get("translation", (0.0, 0.0, 0.0)))),
                    rotation=Quat(*(float(c) for c in value.get("rotation", (1.0, 0.0, 0.0, 0.0)))),
                    scale=Vec3(*(float(c) for c in value.get("scale", (1.0, 1.0, 1.0)))),
                )
        except (TypeError, ValueError):
            # Leave it alone; the operation's own validator will reject it by name, which
            # is a far better message than anything that could be produced here.
            pass
    return out

#: Operation modules that could not be imported at wiring time. Empty is the healthy case;
#: anything in here means those tools are silently unavailable, so callers report it rather
#: than letting an agent discover it by getting an "unknown operation" error mid-build.
MISSING_MODULES: list[str] = []


def _objects_of(result: Any) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Normalise a module's own result type into (produced, modified, removed).

    Each module returns something shaped for its own domain — ``RepairOutcome``,
    ``AlignResult``, ``DetailResult``, ``UVResult``, ``BakeResult``. None of them carries
    the produced/modified/removed triple ``OperationResult`` needs, because none of them
    was written with replay in mind. This reads whatever each one does carry.
    """
    if isinstance(result, OperationResult):
        return (result.produced_objects, result.modified_objects, result.removed_objects)

    produced = tuple(getattr(result, "produced_objects", ()) or ())
    removed = tuple(getattr(result, "removed_objects", ()) or ())

    modified: tuple[str, ...] = ()
    object_id = getattr(result, "object_id", None)
    if object_id:
        # `changed` is DetailResult's and AlignResult's honest "I did nothing" signal. A
        # no-op must not be reported as a modification, or the viewer highlights an object
        # that did not move and the operator loses trust in the highlight.
        changed = getattr(result, "changed", None)
        fixed = getattr(result, "fixed", None)
        if changed is None and fixed is None:
            modified = (object_id,)
        elif changed:
            modified = (object_id,)
        elif fixed:
            modified = (object_id,)

    return (produced, modified, removed)


def _ok_of(result: Any) -> tuple[bool, str, str]:
    """(ok, rule, detail). Modules signal failure differently; none of them raises for a
    merely-unsuccessful outcome, so a truthy default would report every skipped repair as
    a success."""
    if isinstance(result, OperationResult):
        return (result.ok, result.error_rule, result.error_detail)
    ok = getattr(result, "ok", None)
    if ok is None:
        return (True, "", "")
    reason = getattr(result, "unavailable_reason", "") or getattr(result, "reason", "")
    return (bool(ok), "" if ok else "operation.failed", reason)


def adapt(fn: Callable[..., Any], *, id_param: str = "object_id") -> Callable[[EngineProtocol, Operation], OperationResult]:
    """Wrap a plain module function as an ``OperationHandler``.

    ``id_param`` is the parameter carrying the subject's object id; everything else in
    ``op.params`` is forwarded as a keyword argument. Two-object operations (``close_visual_gap``)
    declare their second id in ``params`` like any other argument and need no special case.
    """

    def handler(engine: EngineProtocol, op: Operation) -> OperationResult:
        params = dict(op.params)
        args: list[Any] = [engine]
        if id_param in params:
            args.append(params.pop(id_param))
        try:
            result = fn(*args, **params)
        except TypeError as exc:
            # A parameter mismatch is the agent's mistake, not a crash. Name it.
            return OperationResult(
                op_id=op.op_id,
                ok=False,
                error_rule="operation.bad_parameters",
                error_detail=f"{op.kind}: {exc}",
                error_suggestion=f"check the parameter names for {op.kind}",
            )

        produced, modified, removed = _objects_of(result)
        ok, rule, detail = _ok_of(result)
        return OperationResult(
            op_id=op.op_id,
            ok=ok,
            produced_objects=produced,
            modified_objects=modified,
            removed_objects=removed,
            error_rule=rule,
            error_detail=detail,
        )

    handler.__name__ = getattr(fn, "__name__", "adapted_handler")
    handler.__doc__ = f"Adapted from {getattr(fn, '__module__', '?')}.{handler.__name__}."
    return handler


def build_handlers(*, include_raw: bool = True) -> HandlerRegistry:
    """Every operation the system can replay, keyed by ``Operation.kind``.

    Imports are guarded per module: a module that fails to import costs its own tools, not
    the whole registry. The names are recorded in :data:`MISSING_MODULES` so a caller can
    say which capabilities are absent instead of letting an agent find out by trying.
    """
    MISSING_MODULES.clear()
    registry: HandlerRegistry = {}

    # Every tool's declared schema tells us which of its parameters are points or
    # polylines, so JSON from an agent can be turned into the domain types the operations
    # were written against.
    coercions: dict[str, dict[str, str]] = {}
    for module_name, attr in (
        ("ops", "OP_SPECS"), ("gaps", "GAPS_SPECS"),
        ("align", "ALIGN_SPECS"), ("uv", "UV_SPECS"),
    ):
        try:
            specs = getattr(__import__(module_name), attr, ())
        except Exception:  # noqa: BLE001 — handled again below, where it is reportable
            continue
        for spec in specs:
            coercions[spec.name] = _coercion_map(spec.input_schema)

    def _wrap(kind: str, handler):
        """Coerce, then hand off. Applied to every operation, including ops' own — they
        all receive the same JSON from the same place."""
        mapping = coercions.get(kind, {})
        if not mapping:
            return handler

        def coercing(engine: EngineProtocol, op: Operation) -> OperationResult:
            from dataclasses import replace

            return handler(engine, replace(op, params=coerce_params(op.params, mapping)))

        coercing.__name__ = getattr(handler, "__name__", kind)
        return coercing

    try:
        from ops import OPS

        for kind, handler in OPS.items():
            registry[kind] = _wrap(kind, handler)  # already OperationHandler-shaped
    except Exception as exc:  # noqa: BLE001 — one bad module must not empty the registry
        MISSING_MODULES.append("ops")
        log.error("ops unavailable — no construction operations will work: %s", exc)

    def _add(module_name: str, names: dict[str, str]) -> None:
        try:
            module = __import__(module_name)
        except Exception as exc:  # noqa: BLE001
            MISSING_MODULES.append(module_name)
            log.warning("%s unavailable, its tools are absent: %s", module_name, exc)
            return
        for kind, attr in names.items():
            fn = getattr(module, attr, None)
            if fn is None:
                log.warning("%s.%s missing — %r will not be callable", module_name, attr, kind)
                continue
            registry[kind] = _wrap(kind, adapt(fn))

    _add("gaps", {
        "fill_boundary_holes": "fill_boundary_holes",
        "weld_duplicates": "weld_duplicates",
        "remove_loose": "remove_loose",
        "fix_normals": "fix_normals",
        "split_non_manifold": "split_non_manifold",
        "merge_shells": "merge_shells",
        "close_visual_gap": "close_visual_gap",
        "repair": "repair",
    })
    _add("align", {
        "make_parallel": "make_parallel",
        "make_perpendicular": "make_perpendicular",
        "make_coplanar": "make_coplanar",
        "make_plumb": "make_plumb",
        "make_flush": "make_flush",
        "snap_to_grid": "snap_to_grid",
        "set_angle": "set_angle",
    })
    _add("detail", {
        "apply_edge_treatment": "apply_edge_treatment",
        "add_panel_lines": "add_panel_lines",
        "add_greebles": "add_greebles",
        # Gate B 3.4. Runs by default inside apply_edge_treatment; registered separately
        # so it can be re-run on a mesh bevelled elsewhere, or after a deliberate
        # cleanup=False pass. Real bevels measured mean triangle aspect ratio 109 before
        # this and 64 after.
        "cleanup_bevel_topology": "cleanup_bevel_topology",
    })
    _add("uv", {
        "unwrap_uvs": "unwrap",
        "bake_textures": "bake",
        "unwrap_and_bake": "unwrap_and_bake",
    })

    def phase_promotion(engine: EngineProtocol, op: Operation) -> OperationResult:
        """Record a phase transition. Changes no geometry.

        It still has to be a registered handler: `orchestration.promote()` writes this
        operation into the log so a forced promotion is recorded rather than silent, and
        `scene.apply` looks every `Operation.kind` up in this registry. Without an entry
        here, promoting raised `KeyError` and the phase machine — the backbone of both the
        staged plan and the single-writer design — could not advance at all.
        """
        return OperationResult(op_id=op.op_id, ok=True)

    registry["phase_promotion"] = phase_promotion

    if include_raw:
        try:
            from raw import execute as raw_execute

            def raw_handler(engine: EngineProtocol, op: Operation) -> OperationResult:
                """Raw execution is opaque by construction — it breaks the parametric
                chain and acts as an undo barrier (ADR-009). ``scene.apply`` enforces the
                snapshot requirement; this only has to run it and report honestly."""
                result = raw_execute(engine, op.params.get("source", ""))
                return OperationResult(
                    op_id=op.op_id,
                    ok=result.ok,
                    produced_objects=result.created,
                    removed_objects=result.removed,
                    error_rule=result.error_rule,
                    error_detail=result.error_detail,
                )

            registry["raw_execute"] = raw_handler
        except Exception as exc:  # noqa: BLE001
            MISSING_MODULES.append("raw")
            log.warning("raw unavailable: %s", exc)

    return registry
