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
    "create_texture_material": {"name": "paint", "managed_root": ".textures", "maps": {"albedo": "paint.png"}},
    "update_texture_material": {"name": "paint", "managed_root": ".textures", "maps": {"albedo": "paint.png"}},
    "apply_texture_material": {"preset": "wood", "object_ids": ["hero"]},
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
    "add_gable_roof": {
        "object_id": "roof", "origin": Vec3(0, 0, 2.4), "width": 4.0,
        "depth": 5.0, "pitch_degrees": 30.0, "thickness": 0.16,
        "overhang": 0.3, "trim_width": 0.12, "trim_depth": 0.16,
        "ridge_axis": "y",
    },
    "add_chimney": {
        "object_id": "chimney", "origin": Vec3(0, 0, 3), "width": 0.8,
        "depth": 1.0, "shaft_height": 1.4, "flashing_overhang": 0.18,
        "flashing_height": 0.16, "crown_overhang": 0.1, "crown_height": 0.14,
        "flue_count": 2, "flue_radius": 0.11, "flue_wall_thickness": 0.025,
        "flue_height": 0.5,
        "rim_overhang": 0.03, "rim_height": 0.1,
    },
    "add_impact_head": {
        "object_id": "maul", "origin": Vec3(0, 0, 4), "width": 3.6, "depth": 1.5,
        "height": 1.45, "corner_chamfer": 0.22, "plate_thickness": 0.12,
        "plate_inset": 0.26, "shoulder_depth": 0.38, "shoulder_diameter": 0.88,
        "socket_depth": 0.16, "collar_depth": 0.20, "collar_diameter": 1.24,
        "face_depth": 0.52, "face_diameter": 1.62, "striker_depth": 0.12,
        "striker_socket_depth": 0.05, "striker_diameter": 0.82, "rim_depth": 0.10,
        "rim_overhang": 0.10, "handle_socket_diameter": 0.72,
        "handle_socket_depth": 0.20, "handle_collar_depth": 0.18,
        "handle_collar_overhang": 0.10, "bevel_width": 0.025,
    },
    "add_profiled_solid": {
        "object_id": "bracket", "origin": Vec3(1.0, 2.0, 3.0), "axis": "z",
        "sections": [
            {"offset": 0.0, "profile": [[-0.5, -0.3], [0.5, -0.3], [0.5, 0.3], [-0.5, 0.3]]},
            {"offset": 1.2, "profile": [[-0.2, -0.15], [0.2, -0.15], [0.2, 0.15], [-0.2, 0.15]]},
        ],
        "bevel_width": 0.02,
    },
    "add_opening": {
        "object_id": "opening",
        "wall_id": "wall",
        "position": 2.0,
        "width": 0.9,
        "height": 2.0,
    },
    "add_staircase": {"object_id": "stair", "treads": 6, "rise": 0.18, "run": 0.28, "width": 1.0},
    "add_staircase_to_landing": {
        "object_id": "entry", "landing_id": "landing", "start": Vec3(0, -2, 0),
        "treads": 6, "width": 1.0, "tread_thickness": 0.05,
        "stringer_width": 0.1, "stringer_depth": 0.18,
    },
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
    "add_roof_window": {"object_id": "light", "roof_id": "roof"},
    "add_wall_sign": {"object_id": "sign", "wall_id": "wall"},
    "add_facade_ribs": {"object_id": "ribs", "wall_id": "wall"},
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
