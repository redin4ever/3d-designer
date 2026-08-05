"""Tests for ``unwrap`` — mark seams (agent-supplied or suggested), then unwrap.

``FakeEngine.unwrap`` (``src/testing/fake_surfacing.py``) is a planar XY projection that does
not itself react to which edges are marked as seams — it exists to exercise placement and
bookkeeping, not to reproduce Blender's actual unwrap algorithm. So an explicit ``seams``
override cannot be proven by a *different UV layout* against this fake; it is proven the way
``testing/fake_engine.py``'s own module docstring recommends when geometry cannot show the
difference: by asserting on the recorded interaction (``engine.calls``) and on this module's
own ``UVResult.seam_count``, both of which are real, engine-observed consequences of the
override reaching ``EngineProtocol.mark_seams`` unchanged.
"""

from __future__ import annotations

import pytest

from contracts import Vec3
from testing import FakeEngine
from uv import suggest_seams, unwrap


def test_unwrap_produces_uvs_in_unit_range_and_reports_coverage_in_unit_range(
    engine: FakeEngine,
) -> None:
    engine.create_primitive("box", "cube", Vec3(2.0, 3.0, 1.0))

    result = unwrap(engine, "box")

    uvs = engine.snapshot("box").uvs
    assert uvs is not None and len(uvs) > 0
    assert all(-1e-9 <= u <= 1.0 + 1e-9 and -1e-9 <= v <= 1.0 + 1e-9 for u, v in uvs)
    assert 0.0 <= result.coverage <= 1.0
    assert result.ok is True


def test_unwrap_with_no_seams_argument_marks_the_automatic_suggestion(
    engine: FakeEngine,
) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    expected = suggest_seams(engine.snapshot("box"))

    result = unwrap(engine, "box")

    assert result.seam_count == len(expected)
    call = next(c for c in reversed(engine.calls) if c[0] == "mark_seams")
    _, marked = call[1]
    assert set(marked) == set(expected)


def test_explicit_seams_override_the_suggestion_and_reach_the_engine(
    engine: FakeEngine,
) -> None:
    """The user chose, by name, to be able to override the automatic seam suggestion. This
    proves the override actually took effect two ways: the result's own ``seam_count``
    differs from what the automatic path would have produced, and the exact edge indices
    recorded by ``FakeEngine.mark_seams`` are the caller's, not the suggestion's."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")
    automatic = suggest_seams(snap)
    explicit = (0,)
    assert explicit != automatic and len(explicit) != len(automatic), (
        "test fixture is not exercising a genuine override — pick a different explicit set"
    )

    result = unwrap(engine, "box", seams=explicit)

    assert result.seam_count == len(explicit)
    assert result.seam_count != len(automatic)
    call = next(c for c in reversed(engine.calls) if c[0] == "mark_seams")
    _, marked = call[1]
    assert tuple(marked) == explicit


def test_an_empty_explicit_seams_sequence_is_honoured_not_treated_as_none(
    engine: FakeEngine,
) -> None:
    """``seams=None`` means "decide for me"; ``seams=()`` means "the agent explicitly wants
    no seams at all" — collapsing the two would make it impossible for an agent to ever
    request zero seams."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap(engine, "box", seams=())

    assert result.seam_count == 0
    call = next(c for c in reversed(engine.calls) if c[0] == "mark_seams")
    _, marked = call[1]
    assert tuple(marked) == ()


def test_out_of_range_explicit_seams_are_rejected_before_reaching_the_engine(
    engine: FakeEngine,
) -> None:
    """An out-of-range index would silently seam whichever edge happens to sit at that
    position at the engine end instead, with no error at all — the exact failure
    ``MeshSnapshot.edges()``'s own docstring warns about. This must be caught here, not
    discovered later from a corrupted-looking bake."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")
    out_of_range = len(snap.edges()) + 5

    with pytest.raises(ValueError):
        unwrap(engine, "box", seams=(out_of_range,))


def test_unwrap_passes_method_and_margin_through_to_the_engine(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    unwrap(engine, "box", method="conformal", margin=0.02)

    call = next(c for c in reversed(engine.calls) if c[0] == "unwrap")
    _, method, margin = call[1]
    assert method == "conformal"
    assert margin == pytest.approx(0.02)


def test_unwrap_result_detail_names_the_method(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap(engine, "box", method="conformal")

    assert "conformal" in result.detail
