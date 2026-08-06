"""Tests for ``validate_params`` and ``acceptance_for`` — the entry validation and
definition-of-done halves of every operation in this package (ADR-004, ADR-005).

Both are throwing stubs as of this file (Rule 4 — tests come first); every test below is
expected to fail with ``NotImplementedError`` until the next pass implements them. They
encode the one promise Gate A 4.2 makes non-negotiable: a bad call gets a ``ToolError``
naming the offending parameter and carrying a suggestion, never a bare
``KeyError``/``ValueError``/traceback.
"""

from __future__ import annotations

import pytest

from contracts import AcceptanceQuery, ToolError, Vec3
from ops import OPS, acceptance_for, validate_params

#: One minimal, otherwise-valid params dict per registered kind — used to smoke-test
#: acceptance_for without also exercising validate_params's rejection paths.
_MINIMAL_VALID_PARAMS: dict[str, dict] = {
    # The direct edits (Q-14). Each acts on something that already exists, so the acceptance
    # query is about the object surviving the edit rather than about a shape being built.
    "move_object": {"object_id": "hero", "translation": [1.0, 0.0, 0.0]},
    "rotate_object": {"object_id": "hero", "axis": "z", "degrees": 90.0},
    "scale_object": {"object_id": "hero", "scale": [2.0, 2.0, 2.0]},
    "delete_object": {"object_id": "hero"},
    "duplicate_object": {"object_id": "hero", "new_id": "hero_copy"},
    "rename_object": {"object_id": "hero", "new_id": "hero_renamed"},
    "set_object_material": {"object_id": "hero", "material_id": "seed_paint"},

    "add_primitive": {"object_id": "prim", "kind": "cube", "size": Vec3(1, 1, 1)},
    "add_wall": {
        "object_id": "wall",
        "start": Vec3(0, 0, 0),
        "end": Vec3(4, 0, 0),
        "height": 2.4,
        "thickness": 0.2,
    },
    "add_floor": {"object_id": "floor", "width": 4.0, "depth": 3.0, "thickness": 0.15},
    "add_opening": {
        "object_id": "opening",
        "wall_id": "wall",
        "position": 2.0,
        "width": 0.9,
        "height": 2.0,
    },
    "add_staircase": {"object_id": "stair", "treads": 6, "rise": 0.18, "run": 0.28, "width": 1.0},
    "add_railing": {
        "object_id": "rail",
        "path": [Vec3(0, 0, 0), Vec3(4, 0, 0)],
        "height": 0.9,
        "post_spacing": 1.5,
        "baluster_gap": 0.1,
    },
    "array_along": {"object_id": "arrayed", "path": [Vec3(0, 0, 0), Vec3(4, 0, 0)], "spacing": 1.0},
    "add_lod_chain": {"object_id": "hero", "ratios": (1.0, 0.5, 0.25)},
    "add_modular_kit": {
        "object_id": "kit",
        "grid_size": 0.5,
        "piece_size": Vec3(0.5, 0.5, 0.1),
        "count_x": 3,
        "count_y": 2,
    },
}


# --------------------------------------------------------------------- negative dimension

@pytest.mark.parametrize(
    "kind,params,bad_param",
    [
        (
            "add_wall",
            {
                "object_id": "w",
                "start": Vec3(0, 0, 0),
                "end": Vec3(4, 0, 0),
                "height": -2.4,
                "thickness": 0.2,
            },
            "height",
        ),
        (
            "add_floor",
            {"object_id": "f", "width": 4.0, "depth": -3.0, "thickness": 0.15},
            "depth",
        ),
        (
            "add_railing",
            {
                "object_id": "r",
                "path": [Vec3(0, 0, 0), Vec3(4, 0, 0)],
                "height": -0.9,
                "post_spacing": 1.5,
                "baluster_gap": 0.1,
            },
            "height",
        ),
    ],
)
def test_negative_dimension_is_rejected_naming_the_param(kind, params, bad_param) -> None:
    """A negative height/depth reaching the engine produces an inverted or degenerate
    mesh silently — the same class of failure ``contracts.AABB`` was hardened against.
    Catching it here, named, is what stops an agent from staring at an opaque
    boolean-solver crash three calls later with no idea a -2.4m wall height was the
    actual cause."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)
    assert bad_param in exc.value.detail
    assert exc.value.suggestion


# ----------------------------------------------------------------------------- zero count

@pytest.mark.parametrize(
    "kind,params,bad_param",
    [
        (
            "add_staircase",
            {"object_id": "s", "treads": 0, "rise": 0.18, "run": 0.28, "width": 1.0},
            "treads",
        ),
        (
            "add_modular_kit",
            {
                "object_id": "k",
                "grid_size": 0.5,
                "piece_size": Vec3(0.5, 0.5, 0.1),
                "count_x": 0,
                "count_y": 3,
            },
            "count_x",
        ),
    ],
)
def test_zero_count_is_rejected_naming_the_param(kind, params, bad_param) -> None:
    """A zero-tread staircase or a zero-wide modular kit run is not "an empty but valid
    result" — it is a request nothing was actually built to answer, and the caller must be
    told which count was zero rather than getting an empty scene and no explanation."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)
    assert bad_param in exc.value.detail


# ------------------------------------------------------------------ spacing > path length

@pytest.mark.parametrize(
    "kind,params",
    [
        (
            "add_railing",
            {
                "object_id": "r",
                "path": [Vec3(0, 0, 0), Vec3(2.0, 0, 0)],
                "height": 0.9,
                "post_spacing": 5.0,
                "baluster_gap": 0.1,
            },
        ),
        (
            "array_along",
            {"object_id": "a", "path": [Vec3(0, 0, 0), Vec3(2.0, 0, 0)], "spacing": 5.0},
        ),
    ],
)
def test_spacing_larger_than_the_path_length_is_rejected(kind, params) -> None:
    """A spacing that cannot fit even once along the path is not "one instance at the
    start" silently — it means the requested pitch and the requested path disagree, and an
    agent that does not hear this will not understand why its railing has a single post."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)
    assert "spacing" in exc.value.detail or "path" in exc.value.detail
    assert exc.value.suggestion


# ------------------------------------------------------------------ missing required param

@pytest.mark.parametrize(
    "kind,params,missing",
    [
        (
            "add_wall",
            {"object_id": "w", "start": Vec3(0, 0, 0), "end": Vec3(4, 0, 0), "thickness": 0.2},
            "height",
        ),
        (
            "add_railing",
            {
                "object_id": "r",
                "path": [Vec3(0, 0, 0), Vec3(4, 0, 0)],
                "post_spacing": 1.5,
                "baluster_gap": 0.1,
            },
            "height",
        ),
    ],
)
def test_missing_required_param_is_rejected_by_name(kind, params, missing) -> None:
    """A ``KeyError: 'height'`` three stack frames inside a handler tells an agent nothing
    it can act on. Gate A 4.2's bar is a suggestion specific enough to fix the call in one
    attempt, not a name buried in a traceback."""
    with pytest.raises(ToolError) as exc:
        validate_params(kind, params)
    assert missing in exc.value.detail


def test_validate_params_never_raises_a_bare_key_or_value_error() -> None:
    """Every failure path above must surface as ``ToolError`` specifically — a bare
    ``KeyError``/``ValueError`` reaching an agent is exactly the opaque failure Gate A 4.2
    exists to prevent, and a caller written against ``ToolError`` would not even catch
    either of those by accident."""
    with pytest.raises(ToolError):
        validate_params("add_wall", {})


def test_unknown_kind_is_rejected_by_name_not_a_bare_lookup_failure() -> None:
    """A typo'd operation kind reaching ``OPS[kind]`` directly is a bare ``KeyError`` with
    no list of what the caller could have meant — the same Gate A 4.2 failure mode as a
    bad parameter, just one level up."""
    with pytest.raises(ToolError) as exc:
        validate_params("add_railling", {})
    assert "add_railling" in exc.value.detail


# -------------------------------------------------------------------- acceptance queries

@pytest.mark.parametrize("kind", sorted(OPS))
def test_every_registered_kind_returns_at_least_one_well_formed_acceptance_query(kind) -> None:
    """An operation with no acceptance query is an operation nobody can verify — ADR-005's
    definition-of-done mechanism has nothing to re-run against this operation's own claim
    of success, so a false "done" from the agent is undetectable for this one kind alone."""
    params = _MINIMAL_VALID_PARAMS[kind]

    queries = acceptance_for(kind, params)

    assert len(queries) >= 1
    for q in queries:
        assert isinstance(q, AcceptanceQuery)
