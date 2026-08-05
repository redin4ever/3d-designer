"""Tests for ``UV_SPECS`` — the MCP tool declarations for the polish role.

Mirrors ``src/export/registry_test.py``'s own reasoning: these are real ``ToolSpec`` values
(not stubs, see ``CLAUDE.md``), so the meaningful thing to test is that they satisfy the
invariants ``ToolSpec.__post_init__`` enforces (``contracts/operations.py``) and that
role-partitioning (ADR-003, ADR-007) can actually find and trust them.
"""

from __future__ import annotations

from contracts import ToolRole
from uv import UV_SPECS


def test_uv_specs_is_not_empty() -> None:
    """An empty tuple would mean the polish role has no UV tools to call at all — silently,
    since nothing here would fail at import time to say so."""
    assert len(UV_SPECS) > 0


def test_every_spec_is_visible_to_the_polish_role() -> None:
    """A spec built with the wrong role tuple is invisible to every polish-role agent —
    nobody notices until an agent tries to call the tool by name and it is not there."""
    for spec in UV_SPECS:
        assert ToolRole.POLISH in spec.roles


def test_spec_names_are_unique() -> None:
    """Two tools sharing a name is ambiguous at the MCP dispatch layer — whichever one a
    router resolves first silently shadows the other."""
    names = [spec.name for spec in UV_SPECS]
    assert len(names) == len(set(names))


def test_every_spec_is_mutating() -> None:
    """Both UV tools change the model (UV data or files on disk) — a spec marked
    ``mutating=False`` here would let an inspect-style caller run it without the single
    write lock (ADR-007), racing the one writer actually allowed to change the scene."""
    for spec in UV_SPECS:
        assert spec.mutating is True


def test_no_spec_is_exposed_to_the_inspect_role() -> None:
    """Many inspect agents run concurrently precisely because none of their tools mutate
    (ADR-007) — a mutating UV tool visible to INSPECT would break that guarantee. This is
    also enforced by ``ToolSpec.__post_init__`` itself (``contracts/operations.py``), so this
    test is a second, explicit line of defence at this module's own boundary."""
    for spec in UV_SPECS:
        assert ToolRole.INSPECT not in spec.roles


def test_constructing_the_specs_already_ran_contract_validation() -> None:
    """``ToolSpec.__post_init__`` raises for a mutating tool exposed to INSPECT, or for a
    tool visible to no role at all. ``UV_SPECS`` being importable at all is the proof neither
    mistake is present — this test exists so a future edit that reintroduces one fails here,
    at collection, rather than only for whichever tool someone happens to invoke first."""
    assert all(spec.roles for spec in UV_SPECS)
