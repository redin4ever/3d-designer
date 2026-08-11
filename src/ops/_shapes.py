"""Shape tolerance and degeneracy checks over raw ``params`` — the precise half of F-013.

Gate A 4.2, verbatim, is that the agent is told *what rule it broke*. Everything in this
file exists because ``params`` alone is enough to see one particular class of mistake, and
seeing it here means the agent gets a named rule and an index instead of a bare
``ValueError`` from ``_geom`` or an ``AttributeError`` from a component accessor — which is
what a duplicated path vertex used to produce, three frames below the last code that knew
what a "path" was.

Two jobs, and they are separate on purpose:

**Shape.** ``ops/CLAUDE.md`` says params carry :class:`~contracts.Vec3` and that converting
JSON is the boundary's job (``app/handlers.py``), which is still true — the boundary is
schema-driven and can tell a point from ``add_lod_chain``'s ``ratios``, and nothing here
tries to. But validation now runs on whichever shape arrives *first*: a replayed operation,
a proposal, or a direct call reaches this module before any boundary. So a plain
``[x, y, z]`` is understood rather than crashed on, and normalised so the handler below
sees one shape.

**Degeneracy.** A path of zero length, a duplicated vertex, a direction that points
nowhere. None of these need the engine to detect and all of them destroy geometry if they
reach it. Anything that *does* need live geometry — an opening that misses its wall — stays
in the handler, which has the engine (``architecture.py``).
"""

from __future__ import annotations

from typing import Any

from contracts import EPSILON, ToolError, Vec3

__all__ = [
    "PATH_PARAMS",
    "POINT_PARAMS",
    "as_pair",
    "as_vec3",
    "check_distinct",
    "check_path",
    "normalised_points",
]

#: Which parameters of each kind are a single point or vector. ``size``/``piece_size`` are
#: points in the type sense only — a malformed one is reported as a bad dimension, because
#: that is what the agent has to fix.
POINT_PARAMS: dict[str, tuple[str, ...]] = {
    "add_primitive": ("size",),
    "add_wall": ("start", "end"),
    "add_floor": ("origin",),
    "add_gable_roof": ("origin",),
    "add_staircase": ("origin",),
    "add_staircase_to_landing": ("start",),
    "add_modular_kit": ("piece_size", "origin"),
}

#: Which parameters of each kind are a polyline.
PATH_PARAMS: dict[str, tuple[str, ...]] = {
    "add_railing": ("path",),
    "array_along": ("path",),
}

_DIMENSION_POINTS = frozenset({"size", "piece_size"})


def as_vec3(value: Any, name: str, kind: str, rule: str) -> Vec3:
    """``value`` as a :class:`~contracts.Vec3`, whether it arrived as one or as ``[x, y, z]``.

    ``rule`` is the caller's, not this function's: the same malformed triple is a bad path
    when it is a path point and a bad dimension when it is a ``size``, and the agent needs
    to be told which of its arguments to go and look at.
    """
    if isinstance(value, Vec3):
        return value
    try:
        x, y, z = value
        return Vec3(float(x), float(y), float(z))
    except (TypeError, ValueError):
        raise ToolError(
            rule,
            f"{kind}: {name} is {value!r}, which is not a point",
            f"pass {name} as [x, y, z], three numbers in metres",
        ) from None


def as_pair(value: Any, name: str, kind: str) -> tuple[float, float]:
    """``value`` as a ``(width, depth)`` cross-section pair.

    Unpacking this inline is how ``post_size=[0.05]`` used to reach an agent as ``not
    enough values to unpack (expected 2, got 1)`` — raised inside the validator, the one
    place in this module whose whole job is that no such message is ever produced.
    """
    try:
        w, d = value
        return (float(w), float(d))
    except (TypeError, ValueError):
        raise ToolError(
            "ops.bad_dimension",
            f"{kind}: {name} is {value!r}, which is not a (width, depth) pair",
            f"pass {name} as two positive numbers in metres, e.g. [0.05, 0.05]",
        ) from None


def normalised_points(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``params`` with every point-shaped value of ``kind`` as a ``Vec3``.

    A copy, never in place: ``Operation.params`` is replayed and must stay exactly as it
    was logged.
    """
    out = dict(params)
    for name in POINT_PARAMS.get(kind, ()):
        if name in out:
            rule = "ops.bad_dimension" if name in _DIMENSION_POINTS else "ops.bad_path"
            out[name] = as_vec3(out[name], name, kind, rule)
    for name in PATH_PARAMS.get(kind, ()):
        value = out.get(name)
        if isinstance(value, (list, tuple)):
            out[name] = [
                as_vec3(p, f"{name} point {i}", kind, "ops.bad_path")
                for i, p in enumerate(value)
            ]
    return out


def check_path(path: list[Vec3], kind: str) -> None:
    """Refuse a polyline that describes no run to build along.

    Two distinct failures, deliberately reported differently. Every point the same is a
    caller who meant to name a *run* and named a *position* — telling it a segment is short
    would not land. A duplicated interior vertex is a caller whose path is nearly right and
    who needs the index of the one point to delete.
    """
    if all((p - path[0]).length() < EPSILON for p in path):
        p = path[0]
        raise ToolError(
            "ops.bad_path",
            f"{kind}: all {len(path)} path points are the same point "
            f"({p.x:.4f}, {p.y:.4f}, {p.z:.4f}), so the path has zero length",
            f"pass path points at least {EPSILON:g} m apart — `path` is the run this "
            "operation is built along, not a single position",
        )
    for i, (a, b) in enumerate(zip(path, path[1:])):
        if (b - a).length() < EPSILON:
            raise ToolError(
                "ops.bad_path",
                f"{kind}: path point {i + 1} duplicates point {i} at "
                f"({a.x:.4f}, {a.y:.4f}, {a.z:.4f}), so that segment has zero length",
                f"remove path point {i + 1}, or move it at least {EPSILON:g} m from "
                f"point {i}",
            )


def check_distinct(a: Vec3, b: Vec3, first: str, second: str, kind: str) -> None:
    """Refuse two points that define no direction.

    ``b - a`` is the vector the geometry is swept along. At zero length there is no wall,
    no rail and no prism to build — only the degenerate case ``_geom`` used to catch with a
    bare ``ValueError`` that named neither parameter.
    """
    if (b - a).length() < EPSILON:
        raise ToolError(
            "ops.bad_path",
            f"{kind}: {second} ({b.x:.4f}, {b.y:.4f}, {b.z:.4f}) is coincident with "
            f"{first}, so the direction {second} - {first} has zero length",
            f"pass an {second} at least {EPSILON:g} m from {first}",
        )
