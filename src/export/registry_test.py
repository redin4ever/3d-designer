"""Tests for ``EXPORT_SPECS`` — the MCP tool declarations for the export role.

These are real ``ToolSpec`` values (not stubs, see ``CLAUDE.md``): the meaningful thing to
test is that they satisfy the invariants ``ToolSpec.__post_init__`` enforces
(``contracts/operations.py``) and that role-partitioning (ADR-003) can actually find them —
not any conversion logic, which lives in the other three files.
"""

from __future__ import annotations

from contracts import ToolRole
from export import EXPORT_SPECS


def test_export_specs_is_not_empty() -> None:
    """An empty tuple would mean the export role has no tools to call at all — silently,
    since nothing here would fail at import time to say so, and every export-role agent
    would sit with zero usable tools."""
    assert len(EXPORT_SPECS) > 0


def test_every_spec_is_visible_to_the_export_role() -> None:
    """A spec built with the wrong role tuple is invisible to every export-role agent —
    nobody notices until an agent tries to call the tool by name and it is not there."""
    for spec in EXPORT_SPECS:
        assert ToolRole.EXPORT in spec.roles


def test_spec_names_are_unique() -> None:
    """Two tools sharing a name is ambiguous at the MCP dispatch layer — whichever one a
    router resolves first silently shadows the other, and the shadowed tool becomes
    permanently uncallable with no error anywhere."""
    names = [spec.name for spec in EXPORT_SPECS]
    assert len(names) == len(set(names))


def test_export_scene_tool_is_registered_and_mutating() -> None:
    """The tool that writes a file to disk must be marked ``mutating`` so it requires the
    single write lock (ADR-007) — flagged read-only, it would be free to run concurrently
    with the one agent actually allowed to change the model."""
    spec = next(s for s in EXPORT_SPECS if s.name == "export_scene")
    assert spec.mutating is True
    assert "object_ids" in spec.input_schema.get("required", ())


def test_constructing_the_specs_already_ran_contract_validation() -> None:
    """``ToolSpec.__post_init__`` raises for a mutating tool exposed to INSPECT, or for a
    tool visible to no role at all (see ``contracts/contracts_test.py``). ``EXPORT_SPECS``
    being importable at all is the proof neither mistake is present in this file — this
    test exists so a future edit that reintroduces one fails here, at collection, rather
    than only for whichever tool someone happens to invoke first."""
    assert all(spec.roles for spec in EXPORT_SPECS)
