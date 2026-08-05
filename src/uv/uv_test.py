"""End-to-end tests for the ``uv`` public interface (``src/uv/__init__.py``).

Responsibility-specific behaviour is covered in ``seams_test.py``, ``unwrap_test.py``,
``quality_test.py``, ``bake_test.py``, ``specs_test.py`` and ``results_test.py`` — this file
exercises the barrel's exports together, the way a real caller (an ``ops`` handler, or an MCP
tool dispatch) actually would, rather than one function at a time.
"""

from __future__ import annotations

from contracts import EngineUnavailable, Vec3
from testing import FakeEngine
from uv import (
    UV_SPECS,
    BakeResult,
    UVResult,
    bake,
    suggest_seams,
    unwrap,
    unwrap_and_bake,
    uv_quality,
)


def test_every_public_name_is_importable_from_the_barrel() -> None:
    """``__init__.py`` is a barrel: everything the module brief names must be reachable
    without reaching past it into ``uv.seams``, ``uv.bake``, etc. (``.claude/rules/
    modularity.md``)."""
    assert callable(suggest_seams)
    assert callable(unwrap)
    assert callable(bake)
    assert callable(uv_quality)
    assert callable(unwrap_and_bake)
    assert len(UV_SPECS) > 0
    assert UVResult is not None
    assert BakeResult is not None


def test_suggest_then_unwrap_then_quality_then_bake_is_a_coherent_pipeline(
    engine: FakeEngine,
) -> None:
    """The four public functions named in the module brief chained exactly as an agent
    would: suggest seams, apply them explicitly, check the result, bake."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    snap = engine.snapshot("box")

    chosen_seams = suggest_seams(snap, min_dihedral_deg=45.0)
    uv_result = unwrap(engine, "box", seams=chosen_seams)
    assert uv_result.seam_count == len(chosen_seams)

    quality = uv_quality(engine, "box")
    assert len(quality) == 3

    bake_result = bake(engine, "box")
    assert bake_result.ok is True
    # bake() only unwraps lazily when UVs are missing; this object already has them from the
    # explicit unwrap() call above, so this bake's own uv field stays None (see bake_test.py).
    assert bake_result.uv is None
    assert set(bake_result.maps) == {"albedo", "normal", "roughness"}


def test_unwrap_and_bake_end_to_end_on_a_fresh_object(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap_and_bake(engine, "box")

    assert isinstance(result, BakeResult)
    assert result.ok is True
    assert isinstance(result.uv, UVResult)
    assert result.uv.ok is True


def test_unwrap_and_bake_end_to_end_when_bake_is_unavailable(
    engine_without_bake: FakeEngine,
) -> None:
    """The composed convenience function must carry the exact same ``EngineUnavailable``
    contract as the plain ``bake()`` — never raising, always naming the limitation."""
    engine_without_bake.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap_and_bake(engine_without_bake, "box")

    assert result.ok is False
    assert result.unavailable_reason
    assert result.uv is not None and result.uv.ok is True


def test_engine_unavailable_is_never_raised_out_of_bake_or_unwrap_and_bake(
    engine_without_bake: FakeEngine,
) -> None:
    engine_without_bake.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    try:
        bake(engine_without_bake, "box")
        unwrap_and_bake(engine_without_bake, "box")
    except EngineUnavailable:
        raise AssertionError(
            "EngineUnavailable must be reported on BakeResult, never raised past this module"
        )
