# mcp_server — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions, status, and the reasoning behind the non-obvious
choices, for whoever picks this up next.

## Status

**GREEN.** `pytest src/mcp_server` passes 71/71.

What changed in the Gate B pass, and what it replaced:

- **The role comes from the lease** (ADR-013, Gate B 6.3). `dispatch` no longer consults the
  `role` keyword at all; `authorize.py` asks `Orchestrator.authorize(tool_name, roles,
  lease)` and re-raises its `PhaseViolation` as `PhaseRefusal`, which adds the phase the tool
  *would* be legal in. Before this, `dispatch` checked visibility against the role string the
  caller supplied and never compared it to the session's phase — `unwrap_uvs` (POLISH) and
  `add_railing` (REFINE) both succeeded in `blockout`, and any agent could hold any role by
  naming it.
- **Export actually works** (ADR-014, Gate B 4.1). `export_specs.py` re-issues
  `export.EXPORT_SPECS` with real handlers, so `dispatch` runs them directly against the
  engine outside the operation log. `dispatch("export_scene", ...)` used to raise
  `KeyError: "unknown operation kind 'export_scene'"` — the terminal step of every journey
  had never once worked through the agent's own path.
- **`INSPECT` has tools** (Gate B 3.1). `get_phase`, `list_objects`, `describe_object` and
  (ADMIN) `promote_phase`. The role had zero tools, so a fully autonomous run — Gate A 4.4 —
  could build forever and never promote, never export, never finish.
- **`_cap.py` is deleted** (Gate B 3.3). It trimmed each role to eight and silently hid
  `repair`, `make_plumb` and `close_visual_gap`. Counts are now recorded in
  `registry_test.py` and `README.md`, and logged when a role passes eight.
- **The SDK docs were wrong.** The `mcp`/`mcp_server` collision is fixed, not open; the SDK
  is installed and importable. Both files said otherwise.

Tests came first for every one of those (Rule 4): `authorize_test.py`, `export_tools_test.py`
and `session_tools_test.py` were written against the ADRs and run before any implementation
existed — 35 failures, each on the intended cause (`ToolError: tool 'get_phase' is not
visible`, a call that should have refused and did not, a count that was not recorded). Two
existing `dispatch_test.py` tests were rewritten rather than deleted, and both because the
*contract* they described was superseded by an accepted ADR, which is the only legitimate
reason: one asserted the refusal named the caller's declared role (ADR-013 deletes that
concept — asserting on it would have pinned the exact defect Gate B 6.3 was raised to fix),
and one used `check_export_budget` as the example of a handler-less tool (ADR-014 gives it a
handler). The second kept its subject by building a handler-less spec for the purpose, so the
branch is still covered.

## Commands

```bash
# this module only
python -m pytest src/mcp_server -q

# one file
python -m pytest src/mcp_server/dispatch_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
python -m pytest src -q
```

No `needs_blender` marker anywhere in this module — everything runs against
`orchestration.Orchestrator` backed by this module's own `FakeScene` double (`conftest.py`),
with no Blender, and must stay that way.

## Boundaries

- Write only inside `src/mcp_server/**`. Everything else — `src/contracts/`, `src/ops/`,
  `src/export/`, `src/raw/`, `src/gaps/`, `src/align/`, `src/uv/`, `src/measure/`,
  `src/detail/`, `src/orchestration/`, `src/app/` — is frozen or sibling-owned (Rule 5):
  read freely, never edit.
- `mcp_server/__init__.py` is a barrel: re-exports only.
- Nothing outside `mcp_server/` may import `mcp_server.registry`, `mcp_server.dispatch` etc.
  directly — only `from mcp_server import <name>`. `authorize`, `context`, `validation`,
  `serialize`, `phase_tools` and `scene_query` are module-private and exercised transitively
  through `dispatch`.
- Do not import `bpy`. Nothing here needs it.
- Sibling registry modules (`measure`, `gaps`, `align`, `uv`, `detail`) may not all exist or
  publish a `*_SPECS` constant — `registry._load_optional` guards each one and catches
  broadly, because those modules are built concurrently by separate agents and one can be
  mid-edit at the exact moment this collects from it.

## Implementation notes for whoever picks this up

- **`dispatch`'s check order is deliberate**: find the tool anywhere in the registry ->
  validate params -> require a lease for a mutating tool -> authorise -> execute. Params
  before locks and roles, because a caller with no lease still deserves to learn its params
  are wrong first (`dispatch_test.py::test_missing_parameter_check_runs_before_the_lock_check`).
  A tool that exists but is illegal in this phase gets a *phase* refusal, never "no such
  tool" — those are different problems and an agent handed the wrong one changes the wrong
  thing.
- **`role` is accepted and ignored, not removed.** Callers outside this module's write
  boundary still pass it (`app/app_test.py`, `transports.py`). An ignored keyword is cheaper
  to reverse than one that raises. It is a candidate for deletion in a later reconciliation
  round, once those call sites are updated by their owners.
- **Authorisation delegates; it does not duplicate.** `orchestration.authorize` is the
  authority, including the rule that a lease-less caller reaches `INSPECT` and nothing else
  (not "any read-only tool" — a read-only `EXPORT` tool is still EXPORT's business). The
  local implementation in `authorize.py` is a fallback for an orchestrator predating ADR-013;
  keep the two in step or delete the fallback when nothing needs it.
- **`ToolSpec.handler` is how a tool escapes the operation log.** A handler needs the live
  engine, which no module-level constant can have, so it declares what it needs with
  `context.needs("engine")` / `("orchestrator")` and `dispatch` supplies it at call time.
  That is why the export specs are re-issued here rather than in `export/registry.py` — the
  content is that module's; only the execution route is policy.
- **Nothing may cap or hide a tool.** See `README.md`'s tool-count section. If a role's count
  is inconvenient, the fix is upstream (a coarser role, umbrella tools, per-session
  visibility), never a trim here.
- **No error message may inline the scene.** `describe_object` checks `engine.exists` itself
  and refuses with a count plus six sample ids, precisely so that `EngineProtocol`'s own
  "known objects: ..." — which lists every object — never reaches an agent. A review found
  exactly that dumping all 58 live ids.
- **`_line()` in `phase_tools.py` is ASCII on purpose.** `AcceptanceResult.describe` renders
  an arrow and an em dash; this text goes into exception messages and a Windows console
  whose default encoding is cp1252, where that raises `UnicodeEncodeError` and takes the
  call down. Same reason `contracts.Defect.describe` spells its intersection sign `x`.
- **`downscale_image` operates on binary PPM (`P6`) bytes, not PNG/JPEG.** No Pillow
  dependency here; adding a real codec is a gate decision, not a quiet addition.

## Known gap: the transports are wired against SDK 1.x

The `mcp` SDK **is** installed (2.0.0) and `import mcp` resolves to it — the name collision
is fixed and pinned by a test. But 2.0.0 dropped the low-level `Server.list_tools()` /
`Server.call_tool()` decorators that `_build_server` uses, in favour of
`mcp.server.MCPServer.add_tool`. `_build_server` now detects that and raises one named
`RuntimeError` naming the installed version, rather than an `AttributeError` from inside the
SDK — so the failure is honest, but no live client can connect until it is rewired.

Rewiring is a live-client task: `MCPServer` builds tool schemas by introspecting Python
signatures, while every `ToolSpec` here carries a hand-written JSON Schema, so the mapping
needs verifying against a real session rather than guessed at. Filed rather than attempted.

`_build_server` also now acquires a lease per mutating call under one holder
(`transports._LEASE_HOLDER`), because the transport previously passed no lease at all and
every mutating call over a live connection would have been refused. Same-holder re-acquire
renews, so one connected client is one logical writer and a second server process still
contends properly.

## Test layout

| Test file | Covers |
|---|---|
| `registry_test.py` | recorded per-role counts, nothing hidden, the raw tool's switch and role scoping, description/unit conventions |
| `dispatch_test.py` | param validation, the write lock, the happy path, `raw_execute`'s opaque flag, the handler-less branch |
| `authorize_test.py` | phase gating, the lease as authority, refusal quality, lease-less reads |
| `export_tools_test.py` | both export tools end to end, outside the log, phase-gated |
| `session_tools_test.py` | the four session tools, paging, the unknown-object refusal, promotion with no force |
| `images_test.py` | `downscale_image` |
| `transports_test.py` | `SERVER_INFO`, SDK absence, SDK incompatibility, the ADR-009 loopback warning, the name-collision regression |

`conftest.py` holds `FakeScene` (mirrors, but does not import, `orchestration`'s own private
double) plus the `orchestrator`/`write_lease` fixtures.

## Style

Repository-wide conventions in the root `CLAUDE.md`: dataclasses over dicts,
`from __future__ import annotations`, and a docstring on every test stating the
product-level consequence of it failing — not just what it checks.

## Open items for the main agent

- **`app/app_test.py::test_every_registered_tool_has_a_handler`** counts a tool as executable
  only if its name is an operation kind in `app.handlers`. Ten tools now execute through
  `ToolSpec.handler` instead (six from `measure`, four from here), which is exactly what
  ADR-014 established. The assertion needs to accept either route; it is not this module's
  file to change.
- **`app/app_test.py::test_no_role_exceeds_the_visible_tool_bound`** and
  **`orchestration/phases_test.py::test_tools_for_never_exceeds_the_accuracy_optimal_visible_set`**
  both assert `<= 8` per role. Gate B 3.3 chose to exceed that and measure it, and `inspect`
  is now 9. Both need to become recorded counts rather than a bound, the way
  `registry_test.py` did.
- **`Orchestrator` exposes no `engine`.** `context.engine_of` reaches `.engine`, then
  `.scene.engine`, then `._scene.engine`, and fails by name if none exists. A public
  accessor would remove the last of those.
- **`WriteLease.roles` is never narrowed by any real caller yet.** `acquire(roles=...)`
  exists; nothing in the composition root uses it, so every session holds every role its
  phase allows. Multi-agent partitioning is declared and untested in production shape.
