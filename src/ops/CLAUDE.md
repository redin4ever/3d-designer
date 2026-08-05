# ops — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever writes the bodies of the stubs here.

## Status

**RED by design.** Every function in `primitives.py`, `architecture.py`, `stairs.py`,
`railing.py`, `arrays.py` and `validation.py` raises
`NotImplementedError("ops.<name>: not implemented")`. `OPS` and `OP_SPECS` in `registry.py`
are the one exception — real, fully-constructed data, not stubs (see below). 47 tests exist
across this package: 7 pass today (`registry_test.py`, all against the real registry data),
and 40 are red with `NotImplementedError` until the next pass implements the nine handlers
plus `validate_params`/`acceptance_for`. A change that makes those two counts anything other
than 7 and 40 needs an explanation in the commit message.

The tests were written against the contract in `src/contracts/` and the worked example in
`docs/adr/ADR-004-typed-operations-constraint-placement.md` before any implementation
existed (Rule 4) — they are the spec. Do not change a test to make it pass; if a test seems
wrong, it is describing a real product requirement (re-read ADR-004 before concluding
otherwise).

## Commands

```bash
# this module only
pytest src/ops -q

# one file
pytest src/ops/railing_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker is used anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

## Boundaries

- Write only inside `src/ops/**`. `src/contracts/`, `src/testing/`, and `conftest.py` are
  frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- **Do not depend on `src/constraints/` or `src/measure/` *behaviour*.** Both are stubbed
  themselves (they raise `NotImplementedError` too) even though `.pipeline/modules.json`
  lists them as this module's dependencies for *integration order*. Anything this module
  needs to know about geometry — bounds, triangle counts, transforms — is computed
  directly from `engine.snapshot(...)`/`engine.world_bounds(...)`, the same boundary
  `constraints` itself is built against. When `constraints`/`measure` are later
  implemented, a future pass may choose to route through them (e.g. `add_railing` calling
  `constraints.solve` for post placement instead of hand-rolling the plumb/corner logic) —
  that is an implementation choice for whoever picks up the green pass, not a requirement
  this test suite imposes.
- `ops/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs in
  one of the seven responsibility files instead.
- Nothing outside `ops/` may import `ops.railing`, `ops.stairs`, etc. directly — only
  `from ops import <name>`, per `ops/__init__.py`'s `__all__`.
- Do not import `bpy`. `EngineProtocol` (from `contracts`) is the only engine surface this
  module is written against.

## Implementation notes for whoever picks this up

**`validate_params(kind, params)` takes no `engine` argument, by design.** Everything it
checks is knowable from `params` alone: a negative dimension, a zero count, a missing
required key, or a spacing larger than a `path`'s own arc length (computed from the `path`
list in `params`, not from anything in the engine). Geometry-*dependent* checks — an
opening that does not actually intersect the wall it targets — belong in the handler
itself, which does have `engine`, and must raise `contracts.ToolError` there instead. See
`architecture_test.py::test_opening_entirely_outside_the_wall_raises_tool_error` for the
case this splits on.

**Params carry `contracts.Vec3` directly**, not plain `[x, y, z]` lists — `Operation.params`
is `dict[str, Any]`, and every test in this package constructs params with `Vec3` for any
point/direction value (`path`, `start`, `end`, `origin`, `size`, `piece_size`). `OP_SPECS`'
`input_schema` describes the JSON-over-MCP wire shape (`[x, y, z]` arrays) for the tool
declaration; converting between the two, if ever needed, is `scene`'s or `mcp`'s job at the
boundary, not this module's internal representation.

**The railing's naming convention is part of the contract, not an implementation detail**
(see `railing.py`'s docstring and `railing_test.py::test_add_railing_names_every_part_with_predictable_ids`):

- posts: `f"{op.op_id}_post_{i:03d}"`, arc-length order along the path, corners included.
- balusters: `f"{op.op_id}_baluster_{i:03d}"`, same ordering.
- top rail: `f"{op.op_id}_top_rail"` — exactly one.
- staircase treads: `f"{op.op_id}_tread_{i:03d}"`, climb order, tread 0 lowest.

A later pass extending this module (or `constraints`, once it exists) needs these ids to be
*derivable* without re-running the operation — that is the whole point of the convention,
per ADR-002's "stored, not just applied."

**Spacing and counts are always arc-length quantities**, never straight-line or horizontal
ones. `railing_test.py::test_posts_are_plumb_on_a_31_degree_rake_and_spacing_is_measured_along_the_path`
is the test that exists specifically to catch an implementation that measures a path's
"length" as `hypot(dx, dy)` while ignoring `dz`, or as a straight chord across a multi-point
polyline instead of walking its segments. `testing.mesh_helpers.sample_polyline`,
`arc_length_to` and `tangent_at` (already implemented, real, in `src/testing/`) are the
existing precedent for arc-length-correct pacing along a polyline and are a reasonable
starting point rather than something to reinvent.

**Plumb means the object's own local +Z, after its placed rotation, equals world +Z** —
checked in tests as `engine.snapshot(post_id).transform.rotation.rotate(Vec3(0,0,1)) ≈
Vec3(0,0,1)`. This mirrors `constraints`' own documented `up`/`forward` convention (local
+Z / local +Y in world space) even though this module does not currently call into
`constraints` to get it.

**`add_opening`'s cutter is transient.** The boolean's cutter object must not appear in the
returned `OperationResult` at all — not in `produced_objects`, not left behind in the
engine's object list — only the modified wall, in `modified_objects`.

Keep the one-file-per-responsibility split from `README.md`. An operation's logic that
grows past the 300-line soft cap (`.claude/rules/modularity.md`) wants a private helper
module under `ops/`, not a bigger file crossing the boundary of its own responsibility.

## Test layout

Mirrors the seven responsibility files one-for-one, except `registry.py`, which is tested
by `registry_test.py` (all green — see Status above) rather than following the
throwing-stub pattern the other six do. `railing_test.py` intentionally carries the most
tests: it is this library's flagship, and each of its tests targets one of the four
documented failure modes in `railing.py`'s own module docstring. A new operation kind's
handler test goes in the file matching its responsibility; a new validation or acceptance-
query case goes in `validation_test.py`, parametrized across `OPS` where it naturally
applies to more than one kind.

## Open contract requests

None filed. `contracts.Operation`, `contracts.OperationResult` and `contracts.ToolSpec`
were sufficient to write this module's full test suite without needing to invent a
convention the contract does not already support (contrast `constraints`, which had to
file one for `Placement.up`/`.forward`). If a future implementation pass finds a genuine
gap, file it in `.pipeline/contract-requests.json` rather than editing `src/contracts/`
directly (Rule 5).
