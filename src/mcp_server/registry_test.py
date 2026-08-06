"""Tests for ``build_registry``/``tools_for`` — the role-partitioned tool catalogue every
sub-agent sees (ADR-003).

``build_registry`` and ``tools_for`` are throwing stubs as of this file (Rule 4 — tests
come first); every test below is expected to fail with ``NotImplementedError`` until the
next pass implements them.
"""

from __future__ import annotations

from contracts import ToolRole
from mcp_server import build_registry, tools_for


# ------------------------------------------------------------------- visible-set bounds

#: The visible-set size of every role, recorded rather than assumed (Gate B 3.3).
#:
#: The accuracy-optimal visible tool set measures roughly 5-8, with degradation reported
#: past ~10-15 (``contracts.ToolRole``'s own docstring, ADR-003). Asked at Gate B 3.3
#: whether to split roles further, hide tools, or exceed the band and measure it, the user
#: chose **exceed it and measure**: ship what is needed, record the real numbers, and treat
#: the band as guidance derived from other systems rather than as law here.
#:
#: So this is a ledger, not a limit. A number that changes because a module shipped a tool
#: is a number to *update deliberately* — that act is the measurement the decision asked
#: for. Silently capping the registry to keep a number under 8 is the one response that is
#: ruled out: a fair-capping fallback once did exactly that and hid ``repair``,
#: ``make_plumb`` and ``close_visual_gap``, three core operations, from every agent.
TOOL_COUNTS_BY_ROLE: dict[str, int] = {
    "blockout": 5,
    "refine": 4,
    "repair": 8,
    "align": 7,
    "detail": 4,
    "polish": 2,
    "inspect": 9,
    "export": 2,
    "admin": 2,
}


def test_the_visible_tool_count_of_every_role_is_the_recorded_one() -> None:
    """Gate B 3.3 chose to exceed the 5-8 accuracy band and measure it. That choice is only
    honoured if the number is written down somewhere that fails when it drifts — otherwise
    "we exceeded it deliberately" and "it grew while nobody was looking" are the same
    state, and the next person has a rule instead of evidence.

    If this fails because you added a tool: update the number here and in ``README.md``,
    and do not add a cap to make it go away."""
    actual = {role.value: len(tools_for(role)) for role in ToolRole}
    assert actual == TOOL_COUNTS_BY_ROLE


def test_no_tool_is_hidden_from_the_role_that_declares_it() -> None:
    """The failure this replaces: a fair-capping fallback trimmed each role to eight and
    silently dropped ``repair``, ``make_plumb`` and ``close_visual_gap``. An agent cannot
    call a tool it cannot see, and nothing in the response said anything was missing — the
    operations simply appeared not to exist. Whatever a role's count reaches, every
    declared tool must reach every role that declares it."""
    import mcp_server.registry as registry_module

    registry = build_registry()
    for _source, specs in registry_module._sources(include_raw=True):  # noqa: SLF001
        for spec in specs:
            for role in spec.roles:
                assert spec.name in {s.name for s in registry[role]}, (
                    f"{spec.name} declares role {role.value} but is not visible to it"
                )

    visible = {spec.name for specs in registry.values() for spec in specs}
    for name in ("repair", "make_plumb", "close_visual_gap"):
        assert name in visible, f"{name} is declared but invisible to every role"


def test_catalogue_is_larger_than_any_single_roles_slice() -> None:
    """If the union of every tool were no bigger than the largest role's slice,
    role-partitioning would be doing nothing — every agent could already see everything
    through whichever role happens to have the most tools."""
    registry = build_registry()
    all_names = {spec.name for specs in registry.values() for spec in specs}
    biggest_role = max(len(specs) for specs in registry.values())
    assert len(all_names) > biggest_role


def test_roles_with_real_registered_content_have_at_least_one_tool() -> None:
    """BLOCKOUT/REFINE (``ops.OP_SPECS``, plus ``gaps``/``align`` for REFINE), EXPORT
    (``export.EXPORT_SPECS``), ADMIN (``raw.RAW_TOOL_SPEC``) and POLISH (``uv``'s specs)
    already have real ``ToolSpec`` content declared beside their operations — an empty
    slice for any of these would mean this module dropped already-built tools on the
    floor. INSPECT joined them at Gate B 3.1: session orientation is registry *policy*,
    declared in ``session_specs.py`` here, because the phase and the registry are what it
    reports on and neither belongs to an operation module. DETAIL is still legitimately
    empty — ``detail`` exists but publishes no ``*_SPECS`` constant yet, and asserting >=1
    there would mean this module fabricating tool content ``ARCHITECTURE.md`` assigns
    elsewhere."""
    for role in (
        ToolRole.BLOCKOUT, ToolRole.REFINE, ToolRole.EXPORT, ToolRole.ADMIN,
        ToolRole.POLISH, ToolRole.INSPECT,
    ):
        assert len(tools_for(role)) >= 1, role


def test_build_registry_does_not_crash_when_sibling_spec_constants_are_missing() -> None:
    """``measure``/``detail`` exist but do not publish a ``*_SPECS`` constant yet. A crash
    here would take the whole MCP server down every time one sub-agent module hasn't
    shipped its tool declarations — which, during incremental, parallel module
    construction (Rule 5), is most of the time. Passing today *is* the proof the guarded
    import works, since two of the five optional sources genuinely lack the constant right
    now."""
    registry = build_registry()
    assert isinstance(registry, dict)
    assert set(registry) == set(ToolRole)


def test_build_registry_does_not_crash_when_a_sibling_module_exists_but_fails_to_import(
    monkeypatch,
) -> None:
    """``measure``/``gaps``/``align``/``uv``/``detail`` are, as of this task, being built
    concurrently by separate agents (Rule 5) — one can genuinely exist on disk but be
    mid-edit, momentarily invalid Python, at the exact moment this collects from it.
    ``ImportError``/``AttributeError`` alone is not defensive enough for that: any
    exception while importing an optional source must be treated as "not available yet",
    never allowed to crash registry construction for every other already-working tool."""
    import mcp_server.registry as registry_module

    def _always_raises(name: str):
        raise SyntaxError(f"simulated mid-edit failure importing {name!r}")

    monkeypatch.setattr(registry_module.importlib, "import_module", _always_raises)

    registry = registry_module.build_registry()

    assert isinstance(registry, dict)
    assert set(registry) == set(ToolRole)


# ---------------------------------------------------------------------- INSPECT is inert

def test_no_inspect_tool_is_mutating() -> None:
    """Many INSPECT agents run concurrently precisely because none of their tools can
    mutate (ADR-007) — a single mutating tool here breaks the guarantee the whole
    multi-agent design rests on. ``ToolSpec.__post_init__`` already refuses to *construct*
    the opposite combination, so this is a structural double-check that ``tools_for``
    never mis-routes a mutating spec into this role's slice of a shared registry."""
    for spec in tools_for(ToolRole.INSPECT):
        assert spec.mutating is False, spec.name


# ------------------------------------------------------------------------- the raw tool

def test_build_registry_can_omit_the_raw_tool() -> None:
    """The raw-execution escape hatch (ADR-009) must be switchable off even though it
    ships on by default — a deployment that never wants unrestricted code execution
    reachable needs a way to leave it out entirely, not just hide it behind a role no one
    uses."""
    registry = build_registry(include_raw=False)
    all_names = {spec.name for specs in registry.values() for spec in specs}
    assert "raw_execute" not in all_names


def test_include_raw_defaults_to_true() -> None:
    registry = build_registry()
    assert any(spec.name == "raw_execute" for spec in registry[ToolRole.ADMIN])


def test_raw_tool_is_visible_only_under_admin() -> None:
    """Raw execution has no security boundary of its own (ADR-009) — if it leaked to any
    role besides ADMIN, every agent in that role would gain unrestricted code execution,
    not just the one role meant to hold it."""
    registry = build_registry(include_raw=True)
    for role, specs in registry.items():
        names = {spec.name for spec in specs}
        if role is ToolRole.ADMIN:
            assert "raw_execute" in names
        else:
            assert "raw_execute" not in names, role


# ------------------------------------------------------------------------ descriptions

def test_every_tool_description_is_non_empty() -> None:
    """Tool descriptions measurably change tool-selection accuracy — an empty one gives a
    calling agent nothing to choose the tool by at all."""
    registry = build_registry()
    for specs in registry.values():
        for spec in specs:
            assert spec.description.strip(), spec.name


def test_every_vec3_shaped_parameter_names_its_unit() -> None:
    """Scoped to vec3-shaped parameters (``minItems``/``maxItems`` == 3) rather than every
    numeric dimension in the registry: that is the one convention every current
    ``ToolSpec`` (``ops.OP_SPECS``, ``export.EXPORT_SPECS``) actually and consistently
    follows (``"[x, y, z] in metres."``). Several already-built, frozen tool schemas this
    module may not edit (``add_wall``'s bare ``height``/``thickness``, for one) describe a
    scalar dimension without repeating its unit on that exact field; broadening this
    assertion to every dimension would fail against data outside this module's write
    boundary rather than catching a real regression here — see this task's ``assumptions``
    output."""
    registry = build_registry()
    checked_any = False
    for specs in registry.values():
        for spec in specs:
            for prop_name, prop_schema in spec.input_schema.get("properties", {}).items():
                if prop_schema.get("minItems") == 3 and prop_schema.get("maxItems") == 3:
                    checked_any = True
                    description = prop_schema.get("description", "")
                    assert "metre" in description.lower(), f"{spec.name}.{prop_name}"
    assert checked_any, "expected at least one vec3-shaped parameter in the registry"
