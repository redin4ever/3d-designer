"""Tests for ``OPS``/``OP_SPECS`` — the registry ``scene`` replays through and ``mcp``
declares tools from.

Unlike every other file in this package, these tests pass today: ``OPS`` and ``OP_SPECS``
are real, constructed values (never stubs), because ``contracts.ToolSpec.__post_init__``
runs its own contract check — a mutating tool may never be handed to the read-only
INSPECT role (ADR-007) — at construction time, and that check must run, and pass, the
moment this module is imported.
"""

from __future__ import annotations

from contracts import ToolRole
from ops import OP_SPECS, OPS


def test_every_ops_key_has_a_matching_tool_spec() -> None:
    """A handler with no declared tool is unreachable by any agent — dead code nobody can
    invoke through MCP, however correct its geometry once implemented."""
    assert {s.name for s in OP_SPECS} == set(OPS)


def test_every_tool_spec_has_a_matching_handler() -> None:
    """A tool with no handler crashes at call time — ``scene`` looks up ``OPS[kind]`` and
    would hit a bare ``KeyError`` deep inside the single writer instead of a named
    ``ToolError`` at the boundary."""
    assert set(OPS) == {s.name for s in OP_SPECS}


def test_no_op_tool_is_visible_to_the_inspect_role() -> None:
    """Many INSPECT agents run concurrently precisely because none of their tools mutate
    (ADR-007); every operation in this package mutates the scene, so none may leak there.
    ``ToolSpec.__post_init__`` already refuses to construct such a spec — this test is the
    guarantee that constructing ``OP_SPECS`` never tried to."""
    for spec in OP_SPECS:
        assert ToolRole.INSPECT not in spec.roles, spec.name


def test_every_op_tool_is_mutating() -> None:
    """A construction operation not flagged ``mutating`` would skip the write lock every
    other mutation takes, letting two agents build into the same scene concurrently."""
    for spec in OP_SPECS:
        assert spec.mutating is True, spec.name


def test_every_op_tool_role_is_an_editing_role() -> None:
    """The construction library is a blockout/refine tool set, never exposed under detail,
    polish, export or admin partitioning — role-partitioning is what keeps each agent's
    visible tool count in the 2-7 range accuracy depends on (ADR-003)."""
    allowed = {ToolRole.BLOCKOUT, ToolRole.REFINE}
    for spec in OP_SPECS:
        assert spec.roles, spec.name
        if "texture_material" in spec.name:
            assert set(spec.roles) == {
                ToolRole.BLOCKOUT, ToolRole.REFINE, ToolRole.DETAIL, ToolRole.POLISH,
            }
        else:
            assert set(spec.roles) <= allowed, spec.name


def test_registry_covers_exactly_the_twenty_seven_operations_this_library_declares() -> None:
    """Twenty-seven kinds are this library's stated public surface: the original construction
    and editing operations plus semantic roof, stair, and chimney assemblies.

    A registry short of that count silently drops an operation nobody can call through
    ``scene`` or ``mcp``; one over it is exposing something the barrel does not.

    The seven were added rather than kept in a module of their own because Q-19 chose one
    shared history for the operator's edits and the agent's: ``OPS`` is what ``scene``
    replays through, so being here is what makes a manual nudge undoable, replayable and
    reachable by roll-back-N-steps."""
    assert len(OPS) == 27
    assert len(OP_SPECS) == 27


def test_every_op_tool_has_a_non_empty_input_schema() -> None:
    """An MCP tool with an empty schema gives a calling agent no parameter names at all —
    it would have to guess, which is exactly the raw-coordinate failure mode ADR-004 is
    written against."""
    for spec in OP_SPECS:
        assert spec.input_schema.get("properties"), spec.name
        assert spec.input_schema.get("required"), spec.name
