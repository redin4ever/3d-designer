"""The callables behind ``MEASURE_SPECS``, and the engine they read from.

``mcp_server.dispatch`` raises ``mcp.handler_not_wired`` for a read-only tool whose handler
is ``None``. So a measurement tool declared without one is a tool an agent can see and
cannot call — the same unreachable module in a costlier disguise, which is why these exist.

A handler is built at import time, when no engine exists yet, so the engine arrives by one
of two routes:

1. **At call time**, from the session actually running. ``dispatch`` reads the marker
   ``mcp_server.context.needs("engine")`` sets and passes ``engine=`` alongside the agent's
   parameters. This is the route that is correct when two sessions share one process.
2. **At startup**, from the composition root: ``measure.bind_engine(engine)``. The fallback
   for a caller with no dispatch — this module's own tests, the CLI, a notebook.

``_ENGINE`` is deliberately the only mutable state in this module; everything else stays
pure. Neither route present is a named failure, never ``AttributeError`` on ``None``.

Every handler returns a :class:`contracts.MeasurementReport`, including the ones that
answer with a single number. One return type is what lets ``mcp_server.serialize`` render
any of them without duck-typing, and ``MeasurementReport`` validates on construction that
the scope it declares covers everything it actually looked at.
"""

from __future__ import annotations

from typing import Any, Sequence

from contracts import (
    EngineProtocol,
    JoineryIntent,
    Measurement,
    MeasurementReport,
    ToolError,
)
from spatial import SpatialIndex

from ._errors import require_object, require_objects
from .intersections import find_clipping as _find_clipping
from .metrics import (
    angle_between,
    bounds,
    dimensions,
    distance,
    gap_width,
    surface_angle,
    triangle_count,
    volume,
)
from .neighbours import DEFAULT_MAX_GAP, neighbour_defects, neighbour_pairs
from .report import inspect

__all__ = [
    "bind_engine",
    "reads_geometry",
    "resolve_engine",
    "measure_distance",
    "measure_gap",
    "measure_angle",
    "measure_surface_angle",
    "measure_dimensions",
    "find_clipping",
    "defect_report",
]

#: The attribute ``mcp_server.context.needs("engine")`` sets on a handler, so ``dispatch``
#: hands it the live session's engine at call time. Written here as a literal rather than by
#: importing ``mcp_server``: ``ARCHITECTURE.md``'s arrow runs ``scene -> orchestration ->
#: mcp``, and ``mcp_server.registry`` imports *this* module, so importing it back would both
#: reverse the arrow and close a cycle. If the name ever changes, these handlers stop being
#: handed an engine and fall back to :func:`bind_engine`'s — degraded, never wrong.
_CONTEXT_ATTR = "forge3d_context"

_ENGINE: EngineProtocol | None = None


def reads_geometry(fn):
    """Mark a handler as needing the live engine, and let it be called without one.

    Two routes, deliberately: ``dispatch`` passes ``engine=`` from the session that is
    actually running — which is the correct one when two sessions share a process — and
    :func:`bind_engine` covers a caller that has no dispatch, such as this module's own
    tests and the CLI.
    """
    setattr(fn, _CONTEXT_ATTR, ("engine",))
    return fn


def bind_engine(engine: EngineProtocol | None) -> None:
    """Point every measurement tool at ``engine``. ``None`` unbinds.

    Called once by the composition root, which is the only place that knows which engine
    the process is running (real Blender or the in-memory one). Idempotent and reversible,
    so a test can bind a clean engine and hand it back.
    """
    global _ENGINE
    _ENGINE = engine


def resolve_engine(engine: EngineProtocol | None) -> EngineProtocol:
    """``engine`` if the live call supplied one, else the bound one, else a named failure.

    Never ``AttributeError: 'NoneType' object has no attribute 'snapshot'``: an agent handed
    an opaque error retries the same failing call forever, and a wiring mistake at startup
    would present as a geometry problem it cannot fix.
    """
    if engine is not None:
        return engine
    if _ENGINE is None:
        raise ToolError(
            rule="measure.engine_not_bound",
            detail="no engine is bound and the call supplied none, so nothing can be measured",
            suggestion="the composition root must call measure.bind_engine(engine) at startup; "
            "a tool reached through mcp_server.dispatch is handed one automatically",
        )
    return _ENGINE


def _pair_report(measurement: Measurement, a: str, b: str) -> MeasurementReport:
    return MeasurementReport(measurements=(measurement,), scope=tuple(sorted({a, b})))


def _require_pair(engine: EngineProtocol, a: Any, b: Any) -> tuple[str, str]:
    require_object(engine, a, role="a")
    require_object(engine, b, role="b")
    return (a, b)


def _coerce_joinery(raw: Any) -> tuple[JoineryIntent, ...]:
    """Turn the JSON an agent sends into :class:`contracts.JoineryIntent`.

    Everything crosses the wire as JSON, so a declared joint reaches this module as a plain
    dict. Without this the tool raises ``AttributeError: 'dict' object has no attribute
    'object_id'`` on the first real call, while every test that constructs the dataclass in
    Python stays green — the exact failure ``app/handlers.py`` was written to stop for
    ``Vec3``, one type later.
    """
    if raw is None:
        return ()
    if isinstance(raw, (dict, JoineryIntent)):
        raw = [raw]
    intents: list[JoineryIntent] = []
    for position, item in enumerate(raw):
        if isinstance(item, JoineryIntent):
            intents.append(item)
            continue
        if not isinstance(item, dict):
            raise ToolError(
                rule="measure.bad_joinery",
                detail=f"joinery[{position}] is {type(item).__name__}, not an object",
                suggestion='each entry looks like {"object_id": "post_001", '
                '"into_object_id": "deck", "depth": 0.5, "axis": "z"}',
            )
        try:
            intents.append(
                JoineryIntent(
                    object_id=str(item["object_id"]),
                    into_object_id=str(item["into_object_id"]),
                    depth=float(item["depth"]),
                    tolerance=float(item.get("tolerance", 1e-3)),
                    reason=str(item.get("reason", "")),
                    axis=str(item.get("axis", "")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ToolError(
                rule="measure.bad_joinery",
                detail=f"joinery[{position}] is not a usable declaration: {exc}",
                suggestion="object_id, into_object_id and depth (metres) are all required; "
                "axis is one of 'x', 'y', 'z'",
            ) from exc
    return tuple(intents)


# ------------------------------------------------------------------ the six tools

@reads_geometry
def measure_distance(a: str, b: str, *, engine: EngineProtocol | None = None) -> MeasurementReport:
    engine = resolve_engine(engine)
    _require_pair(engine, a, b)
    return _pair_report(distance(engine, a, b), a, b)


@reads_geometry
def measure_gap(a: str, b: str, *, engine: EngineProtocol | None = None) -> MeasurementReport:
    engine = resolve_engine(engine)
    _require_pair(engine, a, b)
    return _pair_report(gap_width(engine, a, b), a, b)


@reads_geometry
def measure_angle(a: str, b: str, *, engine: EngineProtocol | None = None) -> MeasurementReport:
    engine = resolve_engine(engine)
    _require_pair(engine, a, b)
    return _pair_report(angle_between(engine, a, b), a, b)


@reads_geometry
def measure_surface_angle(
    a: str, b: str, *, engine: EngineProtocol | None = None
) -> MeasurementReport:
    engine = resolve_engine(engine)
    _require_pair(engine, a, b)
    return _pair_report(surface_angle(engine, a, b), a, b)


@reads_geometry
def measure_dimensions(
    object_ids: Sequence[str], *, engine: EngineProtocol | None = None
) -> MeasurementReport:
    engine = resolve_engine(engine)
    ids = require_objects(engine, object_ids)
    measurements: list[Measurement] = []
    for object_id in ids:
        measurements.append(dimensions(engine, object_id))
        measurements.append(bounds(engine, object_id))
        measurements.append(volume(engine, object_id))
        measurements.append(triangle_count(engine, object_id))
    return MeasurementReport(measurements=tuple(measurements), scope=ids)


@reads_geometry
def find_clipping(
    object_ids: Sequence[str],
    joinery: Any = (),
    margin: float = 0.0,
    *,
    engine: EngineProtocol | None = None,
) -> MeasurementReport:
    engine = resolve_engine(engine)
    ids = require_objects(engine, object_ids)
    pairs = neighbour_pairs(engine, ids, margin=margin)
    defects = _find_clipping(engine, pairs, _coerce_joinery(joinery))
    examined = set(ids).union(*(set(pair) for pair in pairs)) if pairs else set(ids)
    return MeasurementReport(defects=defects, scope=tuple(sorted(examined)))


@reads_geometry
def defect_report(
    object_ids: Sequence[str],
    include_neighbours: bool = True,
    joinery: Any = (),
    max_gap: float = DEFAULT_MAX_GAP,
    *,
    engine: EngineProtocol | None = None,
) -> MeasurementReport:
    engine = resolve_engine(engine)
    ids = require_objects(engine, object_ids)
    intents = _coerce_joinery(joinery)

    defects = tuple(d for object_id in ids for d in inspect(engine, object_id))
    examined = set(ids)
    if include_neighbours:
        # One index, shared by both calls: a rebuild re-reads every object's bounds from
        # the engine, and doing that twice per report is the cost ADR-011 exists to avoid.
        index = SpatialIndex(engine)
        index.rebuild()
        for pair in neighbour_pairs(engine, ids, margin=max_gap, index=index):
            examined.update(pair)
        defects += neighbour_defects(
            engine, ids, joinery=intents, max_gap=max_gap, index=index
        )

    measurements = tuple(
        m for object_id in ids for m in (dimensions(engine, object_id), triangle_count(engine, object_id))
    )
    return MeasurementReport(
        measurements=measurements, defects=defects, scope=tuple(sorted(examined))
    )
