"""``validate_params`` and ``acceptance_for`` — entry validation and the definition-of-done
half of every operation in this package (ADR-004, ADR-005).

Every operation's parameters are validated on entry and re-measurable on exit. ADR-005's
programmatic definition-of-done depends on both halves existing: a handler that skips
``validate_params`` lets a negative dimension or an impossible spacing reach the engine as
an opaque failure three calls later; an operation with no ``acceptance_for`` query is an
operation nobody — not the agent, not a QA pass — can verify.

Degenerate *geometry* — a path of zero length, a duplicated vertex, a direction that points
nowhere — is refused here too (F-013, Gate B 5.4), by name and by index, rather than
reaching ``_geom`` as a bare ``ValueError``. The shape-tolerance and degeneracy checks
themselves live in ``_shapes.py``; this file is the per-kind dispatch that decides which
ones apply.
"""

from __future__ import annotations

from typing import Any

from contracts import EPSILON, ToolError, Vec3

from ._acceptance import acceptance_for, runtime_acceptance_for
from ._joinery import joinery_for
from ._geom import path_arc_length
from ._shapes import as_pair, check_distinct, check_path, normalised_points

__all__ = ["validate_params", "acceptance_for", "joinery_for", "runtime_acceptance_for"]

#: Construction kinds validated here (registry_test.py pins the public registry count).
#: literal rather than importing ``registry.OPS`` to avoid a module import cycle:
#: ``registry`` imports every handler module, and every handler module calls into this one.
_KNOWN_KINDS = (
    "add_primitive",
    "add_wall",
    "add_floor",
    "add_gable_roof",
    "add_chimney",
    "add_opening",
    "add_staircase",
    "add_staircase_to_landing",
    "add_railing",
    "array_along",
    "add_lod_chain",
    "add_modular_kit",
)


def _require(params: dict[str, Any], key: str, kind: str) -> Any:
    if key not in params:
        raise ToolError(
            "ops.missing_param",
            f"{kind} is missing required parameter {key!r}",
            f"pass a value for {key!r}",
        )
    return params[key]


def _positive(value: float, name: str, kind: str) -> None:
    if value <= 0:
        raise ToolError(
            "ops.bad_dimension",
            f"{kind}: {name} is {value}, must be > 0",
            f"pass a positive value for {name}",
        )


def _non_negative(value: float, name: str, kind: str) -> None:
    if value < 0:
        raise ToolError(
            "ops.bad_dimension",
            f"{kind}: {name} is {value}, must be >= 0",
            f"pass a value >= 0 for {name}",
        )


def _positive_count(value: int, name: str, kind: str) -> None:
    if value <= 0:
        raise ToolError(
            "ops.bad_count",
            f"{kind}: {name} is {value}, must be >= 1",
            f"pass {name} >= 1",
        )


def _require_path(params: dict[str, Any], kind: str) -> list[Vec3]:
    """The validated polyline: a real list, at least two points, no degenerate segment.

    ``normalised_points`` has already turned any ``[x, y, z]`` entries into ``Vec3``, so
    everything below this line may assume points.
    """
    path = _require(params, "path", kind)
    if not isinstance(path, (list, tuple)):
        raise ToolError(
            "ops.bad_path",
            f"{kind}: path is {path!r}, which is not a list of points",
            "pass `path` as a list of [x, y, z] points, in order along the run",
        )
    if len(path) < 2:
        raise ToolError(
            "ops.bad_path",
            f"{kind}: path has {len(path)} point(s), needs at least 2",
            "pass at least a start and an end point in `path`",
        )
    check_path(path, kind)
    return path


def _check_spacing_fits_path(spacing: float, path: list[Vec3], name: str, kind: str) -> None:
    arc_length = path_arc_length(path)
    if spacing > arc_length + EPSILON:
        raise ToolError(
            "ops.spacing_exceeds_path",
            f"{kind}: {name} {spacing} exceeds the path's own arc length {arc_length:.4f}",
            f"reduce {name} to at most {arc_length:.4f}, or extend the path",
        )


def _validate_pair_param(params: dict[str, Any], key: str, kind: str) -> None:
    """A ``(width, depth)`` cross-section, normalised in place on the already-copied dict so
    the handler downstream unpacks two floats whatever shape arrived."""
    if key not in params:
        return
    w, d = as_pair(params[key], key, kind)
    _positive(w, f"{key}[0]", kind)
    _positive(d, f"{key}[1]", kind)
    params[key] = (w, d)


def validate_params(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """Check ``params`` against ``kind``'s own requirements and return them, normalised.

    **Accepts either shape.** ``ops/CLAUDE.md`` says params carry :class:`~contracts.Vec3`
    and that converting JSON belongs to the boundary (``app/handlers.py``) — still true, and
    still where an agent's call is converted. But validation runs on whichever shape arrives
    first, so a plain ``[x, y, z]`` from a replayed operation or a direct call is understood
    here rather than crashing one layer below with an ``AttributeError`` that cannot name
    the parameter. The returned dict is a **copy** with every point-shaped value as a
    ``Vec3`` and every cross-section pair as a tuple of floats; ``op.params`` itself is
    never touched, because it is replayed and must stay as it was logged.

    See the module docstring and ``ops/CLAUDE.md`` for the bar every raised
    :class:`~contracts.ToolError` here is held to.
    """
    if kind not in _KNOWN_KINDS:
        raise ToolError(
            "ops.unknown_kind",
            f"{kind!r} is not a known operation kind",
            f"use one of: {', '.join(_KNOWN_KINDS)}",
        )

    params = normalised_points(kind, params)
    _require(params, "object_id", kind)

    if kind == "add_primitive":
        _require(params, "kind", kind)
        size = _require(params, "size", kind)
        for axis in ("x", "y", "z"):
            _positive(getattr(size, axis), f"size.{axis}", kind)

    elif kind == "add_wall":
        start = _require(params, "start", kind)
        end = _require(params, "end", kind)
        height = _require(params, "height", kind)
        thickness = _require(params, "thickness", kind)
        _positive(height, "height", kind)
        _positive(thickness, "thickness", kind)
        check_distinct(start, end, "start", "end", kind)

    elif kind == "add_floor":
        width = _require(params, "width", kind)
        depth = _require(params, "depth", kind)
        thickness = _require(params, "thickness", kind)
        _positive(width, "width", kind)
        _positive(depth, "depth", kind)
        _positive(thickness, "thickness", kind)

    elif kind == "add_gable_roof":
        _require(params, "origin", kind)
        for name in ("width", "depth", "thickness", "trim_width", "trim_depth"):
            _positive(_require(params, name, kind), name, kind)
        _non_negative(_require(params, "overhang", kind), "overhang", kind)
        pitch = _require(params, "pitch_degrees", kind)
        if not 0 < pitch < 80:
            raise ToolError(
                "ops.bad_pitch",
                f"{kind}: pitch_degrees is {pitch}, must be between 0 and 80",
                "pass a roof pitch greater than 0 and less than 80 degrees",
            )
        ridge_axis = _require(params, "ridge_axis", kind)
        if ridge_axis not in ("x", "y"):
            raise ToolError(
                "ops.bad_ridge_axis",
                f"{kind}: ridge_axis is {ridge_axis!r}, must be 'x' or 'y'",
                "pass ridge_axis='x' or ridge_axis='y'",
            )

    elif kind == "add_chimney":
        _require(params, "origin", kind)
        for name in (
            "width", "depth", "shaft_height", "flashing_overhang", "flashing_height",
            "crown_overhang", "crown_height", "flue_radius", "flue_height",
            "rim_overhang", "rim_height",
        ):
            _positive(_require(params, name, kind), name, kind)
        count = _require(params, "flue_count", kind)
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 4:
            raise ToolError(
                "ops.bad_count", f"{kind}: flue_count is {count!r}, must be an integer 1..4",
                "pass flue_count as 1, 2, 3, or 4",
            )
        if params["rim_height"] >= params["flue_height"]:
            raise ToolError(
                "ops.bad_dimension",
                f"{kind}: rim_height must be smaller than flue_height",
                "reduce rim_height or increase flue_height",
            )
        rim_diameter = 2.0 * (params["flue_radius"] + params["rim_overhang"])
        crown_width = params["width"] + 2.0 * params["crown_overhang"]
        crown_depth = params["depth"] + 2.0 * params["crown_overhang"]
        along, across = max(crown_width, crown_depth), min(crown_width, crown_depth)
        if rim_diameter > across or count * rim_diameter > along:
            raise ToolError(
                "ops.chimney_flues_do_not_fit",
                f"{kind}: {count} flue rim(s) of diameter {rim_diameter:.4f} m do not fit "
                f"on the {crown_width:.4f} x {crown_depth:.4f} m crown",
                "reduce flue_count, flue_radius, or rim_overhang; or enlarge the crown",
            )
    elif kind == "add_opening":
        _require(params, "wall_id", kind)
        _require(params, "position", kind)
        width = _require(params, "width", kind)
        height = _require(params, "height", kind)
        _positive(width, "width", kind)
        _positive(height, "height", kind)
        if "sill_height" in params:
            _non_negative(params["sill_height"], "sill_height", kind)

    elif kind == "add_staircase":
        treads = _require(params, "treads", kind)
        rise = _require(params, "rise", kind)
        run = _require(params, "run", kind)
        width = _require(params, "width", kind)
        _positive_count(treads, "treads", kind)
        _positive(rise, "rise", kind)
        _positive(run, "run", kind)
        _positive(width, "width", kind)

    elif kind == "add_staircase_to_landing":
        _require(params, "landing_id", kind)
        _require(params, "start", kind)
        treads = _require(params, "treads", kind)
        if treads <= 0:
            raise ToolError(
                "ops.non_positive_count",
                f"{kind}: treads is {treads}, must be >= 1",
                "pass treads >= 1",
            )
        for name in ("width", "tread_thickness", "stringer_width", "stringer_depth"):
            _positive(_require(params, name, kind), name, kind)

    elif kind == "add_railing":
        path = _require_path(params, kind)
        height = _require(params, "height", kind)
        post_spacing = _require(params, "post_spacing", kind)
        baluster_gap = _require(params, "baluster_gap", kind)
        _positive(height, "height", kind)
        _positive(post_spacing, "post_spacing", kind)
        _positive(baluster_gap, "baluster_gap", kind)
        _check_spacing_fits_path(post_spacing, path, "post_spacing", kind)
        for pair_key in ("post_size", "baluster_size", "rail_size"):
            _validate_pair_param(params, pair_key, kind)

    elif kind == "array_along":
        path = _require_path(params, kind)
        spacing = _require(params, "spacing", kind)
        _positive(spacing, "spacing", kind)
        _check_spacing_fits_path(spacing, path, "spacing", kind)

    elif kind == "add_lod_chain":
        ratios = _require(params, "ratios", kind)
        if not ratios:
            raise ToolError(
                "ops.bad_ratios",
                f"{kind}: ratios is empty",
                "pass at least one ratio, the first equal to 1.0",
            )
        for r in ratios:
            if not (0 < r <= 1):
                raise ToolError(
                    "ops.bad_ratios",
                    f"{kind}: ratio {r} must be in (0, 1]",
                    "pass every ratio in the range (0, 1]",
                )
        if ratios[0] != 1.0:
            raise ToolError(
                "ops.bad_ratios",
                f"{kind}: ratios[0] is {ratios[0]}, must be 1.0 — level 0 is the "
                "unmodified hero mesh",
                "set ratios[0] = 1.0",
            )

    elif kind == "add_modular_kit":
        grid_size = _require(params, "grid_size", kind)
        piece_size = _require(params, "piece_size", kind)
        count_x = _require(params, "count_x", kind)
        count_y = _require(params, "count_y", kind)
        _positive(grid_size, "grid_size", kind)
        for axis in ("x", "y", "z"):
            _positive(getattr(piece_size, axis), f"piece_size.{axis}", kind)
        _positive_count(count_x, "count_x", kind)
        _positive_count(count_y, "count_y", kind)

    return params
