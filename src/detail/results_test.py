"""Tests for ``DetailResult`` — real, constructed data, not a stub.

Every other test file in this module constructs one of these from a (currently throwing)
pass and reads it back; if the shape here were wrong — mutable, or missing a field — every
one of those tests would be built on sand. Checked directly and in isolation for that reason.
"""

from __future__ import annotations

import dataclasses

import pytest

from detail import DetailResult


def test_detail_result_is_frozen() -> None:
    """A caller that could mutate a result after receiving it could make ``changed`` say
    something other than what the pass actually did — the report and the geometry would be
    allowed to drift apart with nothing to catch it."""
    result = DetailResult(
        object_id="box", changed=True, triangles_before=12, triangles_after=44, detail="bevel"
    )
    assert result.object_id == "box"
    assert result.triangles_after > result.triangles_before
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.changed = False  # type: ignore[misc]


def test_detail_result_detail_field_defaults_to_empty_string() -> None:
    """A pass that has nothing extra to say should not be forced to invent filler text just
    to satisfy a required field."""
    result = DetailResult(object_id="box", changed=False, triangles_before=12, triangles_after=12)
    assert result.detail == ""
