"""Tests for ``UVResult``/``BakeResult`` — real, constructed dataclasses, not stubs.

A frozen dataclass has no body to implement (see ``detail.results.DetailResult``'s own
docstring for the same argument), so these pass from the moment the file exists; they exist
anyway because every other function in this module needs the exact shape right, and a typo'd
field name here would otherwise only surface the first time some caller happened to read it.
"""

from __future__ import annotations

import dataclasses

import pytest

from uv import BakeResult, UVResult


def test_uv_result_carries_every_field() -> None:
    """A caller reads ``coverage``/``max_stretch``/``overlaps`` straight off this result
    without a second round trip through the engine — if any field were dropped or renamed,
    that shortcut silently stops working."""
    result = UVResult(
        object_id="box", ok=True, seam_count=7, coverage=0.8, max_stretch=1.4, overlaps=0,
        detail="angle_based unwrap",
    )
    assert result.object_id == "box"
    assert result.seam_count == 7
    assert result.coverage == pytest.approx(0.8)
    assert result.max_stretch == pytest.approx(1.4)
    assert result.overlaps == 0
    assert result.detail == "angle_based unwrap"


def test_uv_result_is_frozen() -> None:
    """Mutable outcome data invites a caller to "fix" a result after the fact rather than
    re-running the unwrap — the same reasoning ``contracts.RepairOutcome`` and
    ``detail.EdgeSelection`` are both frozen for."""
    result = UVResult(object_id="box", ok=True, seam_count=1, coverage=0.5, max_stretch=1.0, overlaps=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ok = False  # type: ignore[misc]


def test_bake_result_defaults_to_no_limitation_and_no_uv() -> None:
    """The zero-value defaults must read as "nothing went wrong and nothing extra
    happened" — an ``unavailable_reason`` that defaults to a non-empty string would make
    every successful bake look like a reported limitation."""
    result = BakeResult(object_id="box", ok=True, maps={"albedo": "out/box_albedo.png"})
    assert result.unavailable_reason == ""
    assert result.uv is None


def test_bake_result_carries_a_uv_result() -> None:
    """``unwrap_and_bake`` must be able to nest the exact ``UVResult`` it produced onto the
    ``BakeResult`` it returns — this is the composition the public interface promises."""
    uv = UVResult(object_id="box", ok=True, seam_count=3, coverage=0.9, max_stretch=1.1, overlaps=0)
    result = BakeResult(object_id="box", ok=True, maps={}, uv=uv)
    assert result.uv is uv


def test_bake_result_is_frozen() -> None:
    result = BakeResult(object_id="box", ok=False, maps={}, unavailable_reason="bake needs a window")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ok = True  # type: ignore[misc]
