"""Tests for F-013 (ops half) — degenerate geometry refused by name, before the engine.

Gate A 4.2, verbatim, is that the agent is told *what rule it broke*. The Phase 6 review
found that promise kept for validation failures and broken for geometry ones:
``_geom.oriented_box_between`` raises a bare ``ValueError`` for two coincident points, and
``path_arc_length``/the component accessors raise ``TypeError``/``AttributeError`` for a
path that is not made of points — all of which reach the agent as a raw Python traceback
with no rule, no offending index and nothing to act on.

Everything knowable from ``params`` alone is refused here, in ``validate_params``, with a
:class:`~contracts.ToolError` that names the parameter or the index. Anything only knowable
from live geometry stays in the handler, which has the engine — see
``architecture_test.py::test_opening_entirely_outside_the_wall_raises_tool_error``, which
pins that half of the split and must keep passing.

The second thing pinned here is shape tolerance. ``ops/CLAUDE.md`` says params carry
``contracts.Vec3`` and that JSON conversion belongs to the boundary (``app/handlers.py``),
which is still true — but validation now runs on whichever arrives first, so a plain
``[x, y, z]`` must be understood rather than crash with an ``AttributeError`` one layer
below the only code that could have named it.
"""

from __future__ import annotations

import pytest

from contracts import Operation, ToolError, Vec3
from ops import add_railing, add_wall, validate_params


def _railing(path, **extra) -> dict:
    params = {
        "object_id": "r",
        "path": path,
        "height": 0.9,
        "post_spacing": 1.5,
        "baluster_gap": 0.1,
    }
    params.update(extra)
    return params


def _array(path, spacing: float = 1.0) -> dict:
    return {"object_id": "a", "path": path, "spacing": spacing}


#: The two kinds that take a polyline. Every path check below applies to both, so they are
#: parametrized rather than written out twice (and a third path-taking kind added later
#: only has to join this list).
_PATH_KINDS = [
    pytest.param("add_railing", _railing, id="add_railing"),
    pytest.param("array_along", _array, id="array_along"),
]


# ------------------------------------------------------------------- a path with no length

@pytest.mark.parametrize("kind,build", _PATH_KINDS)
def test_a_path_whose_points_are_all_one_point_is_refused_as_a_bad_path(kind, build) -> None:
    """A railing along a path of zero length is not a short railing — it is a request that
    describes no run at all. Today the caller is told its *spacing* is too large for the
    path, which is true and useless: it sends the agent off shrinking post_spacing forever
    when the actual mistake is two identical path points."""
    params = build([Vec3(2, 2, 0), Vec3(2, 2, 0)])

    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)

    assert exc.value.rule == "ops.bad_path", (
        f"a zero-length path must be named as a path problem, not as {exc.value.rule!r}"
    )
    assert exc.value.suggestion


@pytest.mark.parametrize("kind,build", _PATH_KINDS)
def test_a_zero_length_segment_inside_a_polyline_is_refused_naming_its_index(
    kind, build
) -> None:
    """A duplicated interior vertex is the one degenerate path a human authors by accident —
    click, click again, carry on. It survives every check that only looks at the path's
    total length, and then dies deep in the sweep as ``cannot build a prism between two
    coincident points``, which names neither the parameter nor which of the four points was
    wrong."""
    params = build([Vec3(0, 0, 0), Vec3(2, 0, 0), Vec3(2, 0, 0), Vec3(4, 0, 0)])

    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)

    assert exc.value.rule == "ops.bad_path"
    assert "2" in exc.value.detail, (
        f"the offending index must be in the message, not just 'invalid path': "
        f"{exc.value.detail!r}"
    )
    assert exc.value.suggestion


def test_add_railing_refuses_a_duplicated_path_point_instead_of_a_bare_value_error(
    engine,
) -> None:
    """The handler-level half of the same case, and the one that proves "before it reaches
    the engine". Without the check the first duplicated vertex reaches
    ``oriented_box_between`` while it is sweeping the top rail and raises a bare
    ``ValueError`` — after the posts and balusters have already been created, leaving a
    half-built railing in the scene and a traceback in the agent's context."""
    op = Operation(
        op_id="dup_rail",
        kind="add_railing",
        params=_railing([Vec3(0, 0, 0), Vec3(2, 0, 0), Vec3(2, 0, 0), Vec3(4, 0, 0)]),
    )

    with pytest.raises(ToolError):
        add_railing(engine, op)


@pytest.mark.parametrize("kind,build", _PATH_KINDS)
def test_an_empty_path_is_still_refused_by_name(kind, build) -> None:
    """Regression lock on the check that already exists — an empty point set must keep
    failing as ``ops.bad_path`` and not be swallowed by the new distinct-points check that
    runs beside it."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, build([]))

    assert exc.value.rule == "ops.bad_path"


@pytest.mark.parametrize("kind,build", _PATH_KINDS)
def test_a_path_entry_that_is_not_a_point_is_refused_by_name(kind, build) -> None:
    """``path=[[0,0,0], 4.0]`` is a plausible typo over the wire — one leg written as a
    distance instead of a point. Unrefused it becomes ``unsupported operand type(s) for -:
    'float' and 'list'`` inside a private geometry helper, which tells the agent nothing
    about which of its arguments to fix."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, build([Vec3(0, 0, 0), 4.0]))

    assert exc.value.rule == "ops.bad_path"
    assert exc.value.suggestion


# --------------------------------------------------------------- a zero-length direction

@pytest.mark.parametrize(
    "start,end",
    [
        pytest.param(Vec3(1, 1, 0), Vec3(1, 1, 0), id="vec3"),
        pytest.param([1, 1, 0], [1, 1, 0], id="json-list"),
    ],
)
def test_a_wall_with_no_direction_is_refused_however_its_points_arrived(start, end) -> None:
    """A wall's direction is ``end - start``; when that vector is zero there is no wall to
    build, only a degenerate prism. The Vec3 case is already refused — the JSON case is the
    one that matters, because it is the shape a real agent sends, and it currently dies on
    ``unsupported operand type(s) for -`` before the check that would have named it ever
    runs."""
    params = {"object_id": "w", "start": start, "end": end, "height": 2.4, "thickness": 0.2}

    with pytest.raises(ToolError) as exc:
        validate_params("add_wall", params)

    assert exc.value.rule == "ops.bad_path"
    assert exc.value.suggestion


# ------------------------------------------------------------------ a size with no volume

@pytest.mark.parametrize(
    "kind,params,bad_axis",
    [
        pytest.param(
            "add_primitive",
            {"object_id": "p", "kind": "cube", "size": Vec3(1.0, 0.0, 1.0)},
            "size.y",
            id="add_primitive-vec3",
        ),
        pytest.param(
            "add_primitive",
            {"object_id": "p", "kind": "cube", "size": [1.0, 0.0, 1.0]},
            "size.y",
            id="add_primitive-json-list",
        ),
        pytest.param(
            "add_modular_kit",
            {
                "object_id": "k",
                "grid_size": 0.5,
                "piece_size": [0.5, 0.5, 0.0],
                "count_x": 2,
                "count_y": 2,
            },
            "piece_size.z",
            id="add_modular_kit-json-list",
        ),
    ],
)
def test_a_size_with_a_zero_component_is_refused_naming_the_axis(kind, params, bad_axis) -> None:
    """A flat box is a real modelling request (a plane) but it is never what ``size`` with a
    zero component means — it means one number was dropped. Naming the axis is what makes it
    a one-attempt fix; "invalid size" is what makes it a guess between three."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)

    assert exc.value.rule == "ops.bad_dimension"
    assert bad_axis in exc.value.detail


@pytest.mark.parametrize(
    "bad_pair",
    [
        pytest.param((0.05,), id="one-number"),
        pytest.param(0.05, id="scalar"),
        pytest.param((0.05, 0.0), id="zero-component"),
    ],
)
def test_a_malformed_cross_section_pair_is_refused_not_unpacked(bad_pair) -> None:
    """``post_size`` is a (width, depth) pair. A single number, or a pair with a zero in it,
    is the same dropped-argument mistake as a bad ``size`` — but today the first two shapes
    die on a tuple unpack (``not enough values to unpack``) inside the validator itself,
    which is the one place in this module that is supposed to make that impossible."""
    with pytest.raises(ToolError) as exc:
        validate_params("add_railing", _railing([Vec3(0, 0, 0), Vec3(4, 0, 0)], post_size=bad_pair))

    assert exc.value.rule == "ops.bad_dimension"
    assert "post_size" in exc.value.detail
    assert exc.value.suggestion


# -------------------------------------------------------------- JSON-shaped points are fine

def test_json_shaped_points_validate_and_come_back_as_vec3() -> None:
    """``ops/CLAUDE.md`` says the boundary converts ``[x, y, z]`` to ``Vec3`` and that is
    still where it belongs — but validation now runs on whichever shape arrives first, and
    a caller that reaches this module directly (replay of a logged operation, a proposal, a
    test harness) must get its points understood rather than an ``AttributeError`` from a
    layer that cannot name them."""
    params = validate_params("array_along", _array([[0, 0, 0], [4, 0, 0]], spacing=1.0))

    assert params["path"] == [Vec3(0, 0, 0), Vec3(4, 0, 0)]


def test_a_wall_built_from_json_shaped_points_has_the_length_that_was_asked_for(
    engine,
) -> None:
    """The end-to-end consequence of the line above: an operation replayed from JSON builds
    the geometry it describes instead of failing halfway. Without it, the only thing
    standing between a raw agent call and a traceback is the composition root remembering
    to convert — which is exactly the single point of failure Gate A 4.2 asked to remove."""
    op = Operation(
        op_id="json_wall",
        kind="add_wall",
        params={
            "object_id": "json_wall",
            "start": [0, 0, 0],
            "end": [4, 0, 0],
            "height": 2.4,
            "thickness": 0.2,
        },
    )

    result = add_wall(engine, op)

    bounds = engine.world_bounds(result.produced_objects[0])
    assert bounds.size.x == pytest.approx(4.0, abs=1e-6)
    assert bounds.size.z == pytest.approx(2.4, abs=1e-6)
