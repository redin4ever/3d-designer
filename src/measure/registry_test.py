"""Tests for ``MEASURE_SPECS`` — the tools that make this module reachable at all.

Verified in review before this file existed: ``measure`` published **zero** MCP tool specs.
Every metric and every defect class was implemented, tested and green, and no connected
agent could ask for a distance, a gap, an angle, a clipping check or a defect report. The
product's headline claim is tool-computed spatial truth instead of a model eyeballing a
render; without these declarations that claim is not callable, and the module might as
well not exist.
"""

from __future__ import annotations

import json

import pytest

from contracts import MeasurementReport, ToolError, ToolRole, Transform, Vec3
from measure import MEASURE_SPECS, bind_engine

#: The six an agent cannot work without. More than eight visible tools in one role measures
#: worse than fewer (ADR-003), and this role also carries session tools from elsewhere.
REQUIRED_TOOLS = frozenset(
    {
        "measure_distance",
        "measure_gap",
        "measure_angle",
        "measure_dimensions",
        "find_clipping",
        "defect_report",
    }
)


@pytest.fixture
def bound(engine):
    """Bind the module's tool handlers to a clean engine and unbind afterwards, so one
    test's scene can never leak into another's measurements."""
    bind_engine(engine)
    yield engine
    bind_engine(None)


def _spec(name: str):
    for spec in MEASURE_SPECS:
        if spec.name == name:
            return spec
    raise AssertionError(f"{name!r} is not published; MEASURE_SPECS has {[s.name for s in MEASURE_SPECS]}")


def _box(engine, object_id: str, size: Vec3, at: Vec3) -> None:
    engine.create_primitive(object_id, "cube", size, Transform(translation=at))


# --------------------------------------------------------------- what is published

def test_measure_publishes_the_six_tools_an_agent_cannot_work_without() -> None:
    """Without these names an agent has no way to ask for a number and falls back to
    judging distance from a render — which lands within 2x of ground truth about 37% of the
    time. Every claim this product makes rests on these six being callable."""
    published = {spec.name for spec in MEASURE_SPECS}
    assert REQUIRED_TOOLS <= published, sorted(REQUIRED_TOOLS - published)


def test_every_measure_tool_is_read_only_and_visible_to_inspect() -> None:
    """Any number of INSPECT sub-agents run concurrently precisely because none of their
    tools can mutate (ADR-007). A mutating tool in this role breaks that guarantee for
    every reader at once — `ToolSpec.__post_init__` rejects it, so a regression here shows
    up as an import error rather than a race, and this test says why."""
    for spec in MEASURE_SPECS:
        assert spec.mutating is False, spec.name
        assert spec.roles == (ToolRole.INSPECT,), spec.name


def test_the_published_set_stays_inside_the_accuracy_optimal_bound() -> None:
    """Past roughly eight visible tools in one role, description overlap makes agents
    invent tool names and borrow argument schemas from the wrong tool (ADR-003). This role
    also gains session tools from another module, so measurement grouping its queries is
    what keeps the combined set choosable rather than capped and silently trimmed."""
    assert len(MEASURE_SPECS) <= 8, [spec.name for spec in MEASURE_SPECS]


def test_measure_tools_reach_the_mcp_registry(bound) -> None:
    """`mcp_server.registry._load_optional` collects this module's `MEASURE_SPECS`
    automatically and got `()` from it. This is the test that the wire is connected — every
    other test in this file could pass with the tools still unreachable by any agent."""
    from mcp_server.registry import build_registry

    visible = {spec.name for spec in build_registry()[ToolRole.INSPECT]}
    assert REQUIRED_TOOLS <= visible, sorted(REQUIRED_TOOLS - visible)


# ------------------------------------------------------------------- the schemas

def test_every_parameter_documents_itself_including_its_unit() -> None:
    """A review found `add_opening.position` with no description; an agent guessed
    `[x, y, z]` for a scalar and wasted a round-trip. A schema is what an agent acts on
    without reading source, so an undescribed parameter is a guaranteed wrong call."""
    for spec in MEASURE_SPECS:
        properties = spec.input_schema.get("properties", {})
        assert properties, spec.name
        for name, schema in properties.items():
            description = schema.get("description", "")
            assert len(description) > 15, f"{spec.name}.{name}: {description!r}"
            if schema.get("type") == "number":
                assert any(unit in description for unit in ("metre", "degree")), (
                    f"{spec.name}.{name} is a bare number with no unit: {description!r}"
                )


def test_find_clipping_takes_declared_joinery_including_its_axis() -> None:
    """Nothing anywhere lets an agent declare that a post is *meant* to be 500mm into a
    deck, which is why a staircase plus railing reports 94 clipping defects that are all
    correct joinery. The axis is part of it: the smallest overlap of a post driven through
    a deck is the post's own cross-section, so a depth without an axis permits a post clean
    through."""
    schema = _spec("find_clipping").input_schema["properties"]["joinery"]

    assert schema["type"] == "array"
    entry = schema["items"]["properties"]
    assert {"object_id", "into_object_id", "depth", "axis"} <= set(entry)
    assert set(schema["items"]["required"]) == {"object_id", "into_object_id", "depth"}


def test_every_schema_is_json_serialisable() -> None:
    """These go out over both MCP transports verbatim. A schema carrying a Python object
    an agent never sees serialises fine in a unit test and fails at connect time, taking
    every tool in the role with it."""
    json.dumps([spec.input_schema for spec in MEASURE_SPECS])


# ------------------------------------------------------------------- calling them

def test_measure_distance_returns_a_real_number_through_the_tool_surface(bound) -> None:
    """A published tool with no handler is a tool an agent can see and cannot call —
    `mcp_server.dispatch` raises `mcp.handler_not_wired` for exactly that. Visible but
    inert is the failure this whole item exists to fix."""
    _box(bound, "a", Vec3(1, 1, 1), Vec3(0, 0, 0))
    _box(bound, "b", Vec3(1, 1, 1), Vec3(3, 0, 0))

    report = _spec("measure_distance").handler(a="a", b="b")

    assert isinstance(report, MeasurementReport)
    assert report.measurements[0].value == pytest.approx(2.0, abs=1e-6)
    assert report.measurements[0].unit == "m"


def test_measure_dimensions_groups_the_single_object_metrics(bound) -> None:
    """Four separate tools for size, bounds, volume and triangle count would spend half
    this role's visible-tool budget on one object's numbers. Grouping is what leaves room
    for the checks an agent actually reasons with."""
    _box(bound, "a", Vec3(2, 3, 4), Vec3(0, 0, 0))

    report = _spec("measure_dimensions").handler(object_ids=["a"])

    kinds = {m.kind.value for m in report.measurements}
    assert {"dimensions", "bounds", "volume", "triangle_count"} <= kinds, kinds


def test_find_clipping_accepts_joinery_as_the_plain_json_an_agent_sends(bound) -> None:
    """Every parameter arrives as JSON over the wire — a `JoineryIntent` reaches this
    module as a dict, never as the dataclass its tests construct. Without coercion here the
    tool raises `AttributeError: 'dict' object has no attribute 'object_id'` on the first
    real call while this module's own suite stays green."""
    _box(bound, "deck", Vec3(4, 4, 1), Vec3(0, 0, -0.5))
    _box(bound, "post", Vec3(0.1, 0.1, 2), Vec3(0, 0, 0.5))

    unaware = _spec("find_clipping").handler(object_ids=["post", "deck"])
    assert unaware.defects, "a post 0.5m through a deck was not reported at all"

    declared = _spec("find_clipping").handler(
        object_ids=["post", "deck"],
        joinery=[{"object_id": "post", "into_object_id": "deck", "depth": 0.55, "axis": "z"}],
    )
    assert declared.defects == (), declared.defects


def test_defect_report_declares_the_scope_it_actually_examined(bound) -> None:
    """ADR-011 scopes checks to changed objects plus their neighbours, so a clean report is
    only ever clean *about something*. `MeasurementReport` validates this on construction;
    a report that examined a neighbour without naming it cannot be built at all, and one
    that names too little would let an agent read a partial pass as a whole-scene pass."""
    _box(bound, "deck", Vec3(4, 4, 1), Vec3(0, 0, -0.5))
    _box(bound, "post", Vec3(0.1, 0.1, 2), Vec3(0, 0, 0.5))

    report = _spec("defect_report").handler(object_ids=["post"])

    assert isinstance(report, MeasurementReport)
    assert report.full_scene is False
    assert set(report.scope) >= {"post", "deck"}, report.scope
    assert any(
        {d.object_id, d.other_object_id} == {"post", "deck"} for d in report.defects
    ), report.defects


def test_an_unknown_object_suggests_near_misses_rather_than_the_whole_scene(bound) -> None:
    """Gate A 4.2 asks for a rule and a next step. `align.unknown_object` answers by
    dumping every live object id into its suggestion; at the thousands of objects this
    product targets, that is a next step no agent can act on."""
    _box(bound, "stair_tread_001", Vec3(1, 1, 1), Vec3(0, 0, 0))
    for i in range(60):
        _box(bound, f"filler_{i:03d}", Vec3(1, 1, 1), Vec3(50.0 + 2 * i, 0, 0))

    with pytest.raises(ToolError) as excinfo:
        _spec("measure_distance").handler(a="stair_tred_001", b="stair_tread_001")

    error = excinfo.value
    assert error.rule == "measure.unknown_object"
    assert "stair_tread_001" in error.suggestion
    assert "filler_000" not in error.suggestion, "the whole scene was dumped into a suggestion"
    assert len(error.suggestion) < 400, error.suggestion


def test_every_handler_declares_the_live_engine_it_reads_from(engine) -> None:
    """`mcp_server.dispatch` hands a handler only the context it declared. A measurement
    tool that declares nothing is called with the agent's parameters alone and has no scene
    to read — so it would answer from whatever engine happened to be bound at process
    start, which in a session driving real Blender is the wrong one or none at all."""
    from mcp_server.context import context_for

    scene = type("Scene", (), {"engine": engine})()
    orchestrator = type("Orchestrator", (), {"scene": scene})()

    for spec in MEASURE_SPECS:
        assert context_for(spec.handler, orchestrator) == {"engine": engine}, spec.name


def test_a_handler_handed_an_engine_needs_no_process_wide_binding(engine) -> None:
    """The engine supplied by the live call must win over — and work without — the
    module-level binding. Two sessions in one process, or a test that forgot to unbind,
    would otherwise measure the wrong scene and report it as fact."""
    bind_engine(None)
    _box(engine, "a", Vec3(1, 1, 1), Vec3(0, 0, 0))
    _box(engine, "b", Vec3(1, 1, 1), Vec3(3, 0, 0))

    report = _spec("measure_distance").handler(a="a", b="b", engine=engine)

    assert report.measurements[0].value == pytest.approx(2.0, abs=1e-6)


def test_calling_a_tool_before_the_engine_is_bound_says_what_to_do(engine) -> None:
    """The composition root binds the engine at startup. If it forgets, every measurement
    tool must fail by naming the wiring step rather than raising `AttributeError: 'NoneType'
    object has no attribute 'snapshot'` — an agent handed an opaque error retries the same
    failing call forever."""
    bind_engine(None)

    with pytest.raises(ToolError) as excinfo:
        _spec("measure_distance").handler(a="a", b="b")

    assert excinfo.value.rule == "measure.engine_not_bound"
    assert "bind_engine" in excinfo.value.suggestion
