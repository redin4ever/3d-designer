"""Tests for ``bake`` and ``unwrap_and_bake`` — texture bake, ``EngineUnavailable`` reported
by name, never a crash and never swallowed into a generic failure.
"""

from __future__ import annotations

import pytest

from contracts import EngineError, EngineUnavailable, Vec3
from testing import FakeEngine
from uv import bake, unwrap, unwrap_and_bake


def test_bake_on_engine_without_bake_reports_unavailable_and_does_not_raise(
    engine_without_bake: FakeEngine,
) -> None:
    """In-process ``bpy`` may genuinely have no windowed context to bake with — that must
    arrive as a reported, named limitation, never a crash and never a silent empty result."""
    engine_without_bake.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = bake(engine_without_bake, "box")

    assert result.ok is False
    assert result.unavailable_reason != ""
    assert "bake" in result.unavailable_reason.lower()
    assert result.maps == {}


def test_bake_on_engine_without_bake_still_unwraps_first(
    engine_without_bake: FakeEngine,
) -> None:
    """The UV half of the job is independent of the windowed-context capability the bake
    itself needs — an agent should still learn its object was unwrapped even though baking
    could not proceed."""
    engine_without_bake.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = bake(engine_without_bake, "box")

    assert result.uv is not None
    assert engine_without_bake.snapshot("box").uvs is not None


def test_bake_before_any_unwrap_unwraps_first(engine: FakeEngine) -> None:
    """Documented policy (see README.md): ``bake()`` unwraps lazily rather than demanding a
    prior ``unwrap()`` call and failing when one is missing."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    assert engine.snapshot("box").uvs is None

    result = bake(engine, "box")

    assert result.ok is True
    assert result.uv is not None
    assert engine.snapshot("box").uvs is not None
    assert set(result.maps) == {"albedo", "normal", "roughness"}


def test_bake_does_not_reunwrap_an_object_that_already_has_uvs(engine: FakeEngine) -> None:
    """An object explicitly unwrapped with caller-chosen seams must not have that choice
    silently overwritten just because ``bake()`` was called next — only the missing-UV case
    triggers the lazy auto-unwrap."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    unwrap(engine, "box", seams=(0, 1))

    result = bake(engine, "box")

    assert result.uv is None, "bake() re-unwrapped an object that already had UVs"


def test_baking_an_unknown_channel_name_does_not_crash(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = bake(engine, "box", channels=("totally_unknown_channel",))

    assert result.ok is True
    assert "totally_unknown_channel" in result.maps


def test_bake_propagates_a_non_unavailable_engine_error_rather_than_swallowing_it(
    engine: FakeEngine,
) -> None:
    """``EngineUnavailable`` is one specific, named failure — a *different* engine error (a
    bad resolution, here) must never be caught and reshaped into the same ``ok=False,
    unavailable_reason=...`` bucket, or an agent could no longer tell "install Blender's
    dependencies" apart from "your resolution argument is wrong"."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    unwrap(engine, "box")

    with pytest.raises(EngineError) as exc:
        bake(engine, "box", resolution=999)

    assert not isinstance(exc.value, EngineUnavailable)
    assert exc.value.rule == "engine.bad_resolution"


def test_unwrap_and_bake_carries_the_uv_result_through(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap_and_bake(engine, "box", seams=(0, 1, 2))

    assert result.ok is True
    assert result.uv is not None
    assert result.uv.seam_count == 3
    assert set(result.maps) == {"albedo", "normal", "roughness"}


def test_unwrap_and_bake_always_reunwraps_even_if_uvs_already_exist(
    engine: FakeEngine,
) -> None:
    """Unlike ``bake()``, calling ``unwrap_and_bake()`` is itself the request to (re)unwrap —
    a fresh ``seams`` override must reach the engine even for an object baked once already."""
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))
    unwrap(engine, "box", seams=(0,))

    result = unwrap_and_bake(engine, "box", seams=(0, 1, 2, 3))

    assert result.uv is not None
    assert result.uv.seam_count == 4


def test_unwrap_and_bake_reports_unavailable_without_raising(
    engine_without_bake: FakeEngine,
) -> None:
    engine_without_bake.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap_and_bake(engine_without_bake, "box")

    assert result.ok is False
    assert result.unavailable_reason != ""
    assert result.uv is not None, "the unwrap half should still have succeeded"


def test_unwrap_and_bake_passes_bake_kwargs_through(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    result = unwrap_and_bake(
        engine, "box", channels=("albedo",), resolution=512, output_dir="out/dir"
    )

    assert result.maps == {"albedo": "out/dir/box_albedo.png"}


def test_unwrap_and_bake_rejects_an_unknown_keyword(engine: FakeEngine) -> None:
    engine.create_primitive("box", "cube", Vec3(1.0, 1.0, 1.0))

    with pytest.raises(TypeError):
        unwrap_and_bake(engine, "box", not_a_real_kwarg=True)
