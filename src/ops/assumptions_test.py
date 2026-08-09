"""Tests for F-021 — every dimension this library supplied, reported back (Gate B 1.4).

Gate A 6.4, in the user's own framing, chose that this tool never carries a table of
real-world dimensions: the agent supplies every one. The Phase 6 drift review found
``add_railing`` quietly defaulting three cross-sections — 50mm posts, 30mm balusters, a
50mm rail — invisibly. Gate B kept the defaults and required them *reported*:
``OperationResult.assumptions`` carries one human-readable line per value the handler
supplied because the caller omitted it, and ``ActionReport`` renders it as ``ASSUMED ...``.

An agent that can see what was assumed on its behalf can correct it. One that cannot is
being handed a hidden dimension table under another name, which is the thing Gate A 6.4
refused.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from contracts import Operation, Vec3
from ops import OPS
from textures import TextureLibrary

_TEXTURE_ROOT = Path(tempfile.mkdtemp(prefix="forge3d-texture-ops-"))
_TEXTURE_FIXTURE = Path(__file__).parents[1] / "textures" / "fixtures" / "pixel.png"

# ------------------------------------------------------------------ shared fixtures/helpers

#: One minimal, otherwise-valid params dict per registered kind — deliberately *minimal*,
#: i.e. every optional parameter omitted, so the sweep below sees every default this
#: library carries.
_MINIMAL_PARAMS: dict[str, dict] = {
    "create_texture_material": {"object_id": "texture-library", "name": "create_assumption", "managed_root": str(_TEXTURE_ROOT), "maps": {"albedo": str(_TEXTURE_FIXTURE)}},
    "update_texture_material": {"object_id": "texture-library", "name": "update_assumption", "managed_root": str(_TEXTURE_ROOT), "maps": {"albedo": str(_TEXTURE_FIXTURE)}},
    "apply_texture_material": {"object_id": "hero", "preset": "wood", "object_ids": ["hero"]},
    # The direct edits (Q-14). Each takes an object that already exists rather than making
    # one, so they name `hero` from _seed. Included in the sweep for the same reason as
    # everything else: an operation that reports an assumption about a parameter the caller
    # supplied makes the whole ASSUMED block untrustworthy, and these are operations too.
    "move_object": {"object_id": "hero", "translation": [1.0, 0.0, 0.0]},
    "rotate_object": {"object_id": "hero", "axis": "z", "degrees": 90.0},
    "scale_object": {"object_id": "hero", "scale": [2.0, 2.0, 2.0]},
    "delete_object": {"object_id": "hero"},
    "duplicate_object": {"object_id": "hero", "new_id": "hero_copy"},
    "rename_object": {"object_id": "hero", "new_id": "hero_renamed"},
    "set_object_material": {"object_id": "hero", "material_id": "seed_paint"},
    "add_primitive": {"object_id": "prim", "kind": "cube", "size": Vec3(1, 1, 1)},
    "add_wall": {
        "object_id": "wall2",
        "start": Vec3(0, 5, 0),
        "end": Vec3(4, 5, 0),
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
    "add_lod_chain": {"object_id": "hero", "ratios": (1.0, 0.5)},
    "add_modular_kit": {
        "object_id": "kit",
        "grid_size": 0.5,
        "piece_size": Vec3(0.5, 0.5, 0.1),
        "count_x": 3,
        "count_y": 2,
    },
}


def _seed(engine) -> None:
    """The objects the target-taking operations need to already exist."""
    from ops import add_primitive, add_wall

    add_wall(
        engine,
        Operation(
            op_id="seed_wall",
            kind="add_wall",
            params={
                "object_id": "wall",
                "start": Vec3(0, 0, 0),
                "end": Vec3(4, 0, 0),
                "height": 2.4,
                "thickness": 0.2,
            },
        ),
    )
    for name in ("arrayed", "hero"):
        add_primitive(
            engine,
            Operation(
                op_id=f"seed_{name}",
                kind="add_primitive",
                params={"object_id": name, "kind": "cube", "size": Vec3(0.4, 0.4, 0.4)},
            ),
        )
    # The direct edits added at Q-14 target existing things rather than creating them, so the
    # sweep needs a material to exist as well as an object.
    engine.create_material("seed_paint", (0.5, 0.5, 0.5))
    library = TextureLibrary(_TEXTURE_ROOT)
    try:
        library.get("update_assumption")
    except KeyError:
        library.create("update_assumption", {"albedo": _TEXTURE_FIXTURE})


def _railing_op(op_id: str = "rail", **extra) -> Operation:
    params: dict = {
        "object_id": op_id,
        "path": [Vec3(0, 0, 0), Vec3(4.0, 0, 0)],
        "height": 0.9,
        "post_spacing": 1.5,
        "baluster_gap": 0.1,
    }
    params.update(extra)
    return Operation(op_id=op_id, kind="add_railing", params=params)


def _lines_naming(result, param: str) -> list[str]:
    return [line for line in result.assumptions if param in line]


# ---------------------------------------------------------------- the railing's three defaults

def test_an_omitted_post_size_is_reported_back_to_the_agent(engine) -> None:
    """This is the exact defect Gate B 1.4 was raised on. An agent that asks for a railing
    and never names a post cross-section gets 50mm posts; if that number does not come back
    it cannot know a decision about size was taken for it, so it cannot correct the one
    thing most likely to be wrong for its scene's scale."""
    from ops import add_railing

    result = add_railing(engine, _railing_op())

    lines = _lines_naming(result, "post_size")
    assert lines, f"post_size was defaulted but not reported: {result.assumptions}"
    assert "0.05" in lines[0], f"the reported line must name the value used: {lines[0]!r}"


def test_a_supplied_post_size_is_not_reported_as_an_assumption(engine) -> None:
    """An assumption report that also lists what the agent itself passed is noise, and
    noise is how a real assumption gets skimmed past. Only values the tool chose belong
    here."""
    from ops import add_railing

    result = add_railing(engine, _railing_op(post_size=(0.09, 0.09)))

    assert not _lines_naming(result, "post_size"), (
        f"post_size was supplied by the caller and must not be reported: {result.assumptions}"
    )


def test_every_omitted_railing_cross_section_is_reported_once(engine) -> None:
    """Three separate dimensions are defaulted, not one. Reporting only the post size would
    leave the balusters and the rail exactly as invisible as all three were before —
    partial disclosure reads as full disclosure to whoever is reading the report."""
    from ops import add_railing

    result = add_railing(engine, _railing_op())

    for param, value in (("post_size", "0.05"), ("baluster_size", "0.03"), ("rail_size", "0.05")):
        lines = _lines_naming(result, param)
        assert len(lines) == 1, f"expected exactly one line for {param}: {result.assumptions}"
        assert value in lines[0], f"{param}'s line must name the value used: {lines[0]!r}"


def test_a_railing_given_every_dimension_reports_no_assumptions(engine) -> None:
    """When the agent supplies every dimension the tool has assumed nothing, and the report
    must say so by staying empty. A report that always carries lines teaches the reader to
    ignore it."""
    from ops import add_railing

    result = add_railing(
        engine,
        _railing_op(post_size=(0.08, 0.08), baluster_size=(0.02, 0.02), rail_size=(0.06, 0.04)),
    )

    assert result.assumptions == (), f"nothing was assumed, yet: {result.assumptions}"


def test_the_reported_default_is_the_dimension_actually_built(engine) -> None:
    """A report is only worth the geometry it describes. If the line says 0.05 x 0.05 m and
    the post is built at some other size, the agent has been given a *wrong* number to
    correct against — worse than no number, because it will be trusted."""
    from ops import add_railing

    result = add_railing(engine, _railing_op())

    post = next(pid for pid in result.produced_objects if "_post_" in pid)
    size = engine.world_bounds(post).size
    assert size.x == pytest.approx(0.05, abs=1e-6)
    assert size.y == pytest.approx(0.05, abs=1e-6)
    assert "0.05" in _lines_naming(result, "post_size")[0]


# ----------------------------------------------------------------------------- the sweep

@pytest.mark.parametrize("kind", sorted(OPS))
def test_no_operation_reports_an_assumption_for_a_parameter_the_caller_supplied(
    kind, engine
) -> None:
    """The sweep Gate B 1.4 asked for, held as an invariant rather than a one-off audit: an
    operation may report only what it chose itself. A handler that names a parameter the
    caller passed is either reporting the wrong value or reporting the wrong parameter, and
    both make the whole ``ASSUMED`` block untrustworthy for every other operation too."""
    _seed(engine)
    params = _MINIMAL_PARAMS[kind]
    op = Operation(op_id=params["object_id"], kind=kind, params=params)

    result = OPS[kind](engine, op)

    assert isinstance(result.assumptions, tuple)
    for line in result.assumptions:
        assert isinstance(line, str) and line.strip(), f"{kind}: empty assumption line"
        for supplied in params:
            assert not line.startswith(supplied), (
                f"{kind} reported {supplied!r} as assumed, but the caller passed it"
            )
