"""Tests for ``DETAIL_SPECS`` — the MCP tool declarations for the detail role.

F-008, verified in review: the ``DETAIL`` role had **zero** tools. Every function in this
module was built, tested and correct, and none of it could be called by anything — the three
detail passes were named first-class at Gate A 8.4 and are a large part of why this product
exists, since the user's complaint (Gate A 1.3) was models that look like *"stitched together
cubes"*.

``mcp_server/registry.py::_load_optional`` picks up a module's ``*_SPECS`` constant
automatically and was, until this file existed, getting ``()`` from ``detail``.

The parameter-description tests below are not style policing. An agent acts on the schema
alone; a review found one parameter with no description cost a wasted round-trip because the
agent guessed a vector where a scalar was wanted.
"""

from __future__ import annotations

from contracts import ToolRole, ToolSpec
from detail import DETAIL_SPECS


def test_the_detail_role_has_tools_at_all() -> None:
    """The defect itself. An empty tuple fails nothing at import time and reads as "this
    module has no tools yet" rather than "three shipped passes are unreachable"."""
    assert len(DETAIL_SPECS) >= 3


def test_all_three_named_passes_are_published() -> None:
    """Gate A 8.4 named edge treatment, panel lines and greebles. Publishing two of three
    leaves a shipped, tested pass permanently uncallable — and nothing else in the product
    would report it missing."""
    names = {spec.name for spec in DETAIL_SPECS}

    assert any("bevel" in n or "edge" in n for n in names)
    assert any("panel" in n for n in names)
    assert any("greeble" in n for n in names)


def test_every_spec_is_visible_to_the_detail_role_and_marked_mutating() -> None:
    """A spec with the wrong role is invisible to every detail-role agent, and one that
    forgets ``mutating`` would be free to run beside the single writer — these passes all
    change geometry (ADR-007)."""
    for spec in DETAIL_SPECS:
        assert isinstance(spec, ToolSpec)
        assert ToolRole.DETAIL in spec.roles
        assert spec.mutating is True


def test_spec_names_are_unique_and_do_not_collide_with_other_modules() -> None:
    """Two tools sharing a name is ambiguous at MCP dispatch: whichever the router resolves
    first silently shadows the other, and the shadowed tool becomes uncallable with no error
    anywhere."""
    from export import EXPORT_SPECS
    from ops import OP_SPECS

    names = [spec.name for spec in DETAIL_SPECS]
    assert len(names) == len(set(names))
    others = {s.name for s in OP_SPECS} | {s.name for s in EXPORT_SPECS}
    assert not (set(names) & others)


def test_every_parameter_carries_a_description(  ) -> None:
    """An agent acts on the schema alone. A review found a parameter with no description cost
    a wasted round-trip because the agent guessed a vector where a scalar was wanted — the
    fix is not "write better prompts", it is that every parameter says what it is."""
    for spec in DETAIL_SPECS:
        for name, schema in spec.input_schema["properties"].items():
            assert schema.get("description"), f"{spec.name}.{name} has no description"


def test_every_measurement_parameter_states_its_unit() -> None:
    """Metres or degrees or a fraction — a bevel width of "2" is either a reasonable 2 mm or
    an object-destroying 2 m, and the agent has no way to tell from a bare number. Every
    numeric parameter must name its unit in its description."""
    unitless = {"segments", "seed", "axis"}
    for spec in DETAIL_SPECS:
        for name, schema in spec.input_schema["properties"].items():
            if schema.get("type") != "number" or name in unitless:
                continue
            text = schema["description"].lower()
            assert any(u in text for u in ("metre", "meter", "degree", "fraction", "per ")), (
                f"{spec.name}.{name} does not state its unit: {schema['description']!r}"
            )


def test_every_spec_declares_what_it_requires() -> None:
    """Every one of these passes acts on a named object. A schema with no ``required`` list
    lets an agent call the tool with no object at all and discover the problem from a
    ``KeyError`` rather than from the schema."""
    for spec in DETAIL_SPECS:
        assert "object_id" in spec.input_schema.get("required", ())


def test_the_bevel_tool_can_report_which_edges_it_chose_and_why() -> None:
    """The bevel pass selects edges heuristically and already records its reasons. Surfacing
    them — "8 of 18 edges, because they are convex and over 30 degrees" — is the stated
    reasoning that makes an agent's next call better; hiding it leaves the agent guessing at
    a heuristic it cannot see."""
    spec = next(s for s in DETAIL_SPECS if "bevel" in s.name or "edge" in s.name)

    text = f"{spec.description} {' '.join(spec.examples)}".lower()
    assert "reason" in text or "why" in text or "which edges" in text


def test_every_spec_carries_at_least_one_example() -> None:
    """``ToolSpec.examples`` are what an agent pattern-matches a user's phrasing against.
    A tool with none is one an agent has to infer the calling convention for."""
    for spec in DETAIL_SPECS:
        assert spec.examples


def test_the_registry_actually_picks_the_specs_up() -> None:
    """The whole point of F-008. ``mcp_server.registry._load_optional`` collects
    ``detail.DETAIL_SPECS`` by name; if the constant is not exported from the package barrel
    it silently returns ``()`` and the DETAIL role stays empty exactly as before."""
    from mcp_server.registry import build_registry

    published = {spec.name for spec in build_registry()[ToolRole.DETAIL]}

    assert published, "the DETAIL role is still empty"
    assert published & {spec.name for spec in DETAIL_SPECS}
