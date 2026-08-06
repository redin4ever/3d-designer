# Experience — walking the journeys

## Method

Everything below was run live against `sys.path.insert(0,'src'); from app import build_app;
app = build_app(prefer_blender=True)` (`engine: bpy-5.2.0 LTS`, confirmed by
`python src/forge3d_cli.py doctor`). Tool calls went through the real agent path —
`mcp_server.dispatch(name, params, role=..., orchestrator=app.orchestrator, lease=lease)` —
not module functions called directly, except where marked as a deliberate bypass. Scripts
are in the scratchpad; every number below is **observed**, pasted from real output, unless
marked **inferred**. QA suites were not re-run; `docs/qa/report-1.md` is cited only where
it corroborates something independently reproduced here.

## Journey by journey

### 1. First contact

`doctor` reports 32 operations registered, but the MCP-visible surface
(`mcp_server.build_registry()`) is **29** `ToolSpec`s across 9 roles: blockout(5),
refine(4), repair(8), align(7), **detail(0)**, polish(2), **inspect(0)**, export(2),
admin(1). `add_wall`'s schema is a good example of self-sufficient: `start`/`end`
documented `"[x, y, z] in metres"`, `height`/`thickness` typed with `exclusiveMinimum`.

I picked `add_opening` and called it as the surrounding vec3-heavy API suggests —
`position: [1.0, 0, 0]` — because nothing in the schema (no `description` on that field)
says it's a scalar. It failed instantly: `mcp.invalid_parameter_type: 'add_opening'
parameter 'position' must be of type 'number', got list — pass a number value for
'position'`. Recoverable in one attempt (names the parameter and type), but not what
`position` *means* (distance from which end of the wall). Attempt two succeeded only
because it was the only number left to try. Missing-required-parameter and unknown-tool
errors are similarly one-shot recoverable: `mcp.missing_parameter` names the field;
`mcp.tool_not_visible` lists every tool the role *can* call. Gate A 4.2's promise ("what
rule it broke") holds for validation-layer failures.

It does not hold for `export_scene`. Calling it through `dispatch` — the only way an
agent reaches it — raises a raw `KeyError` from `src/scene/document.py:94`, dumping every
known operation kind, not a `ToolError`. No rule name, no suggestion. Cause:
`export_scene`/`check_export_budget` were never wired into the handler registry —
`app_test.py`'s own `test_every_registered_tool_has_a_handler` special-cases them out of
the check rather than asserting they work. More in Journey 7.

Second discovery: **two disconnected tool catalogs**. `mcp_server.registry` is the real
one `dispatch` uses. `orchestration._tool_registry.TOOLS_BY_ROLE` is a second, static
table `Orchestrator.tools_for(role)` reads instead — the method a phase-aware "what can I
do now" query would call. Its 16 names (`duplicate_object`, `align_face`, `bevel_edges`,
`export_gltf`, `promote`-adjacent `checkpoint`/`rollback`, etc.) match **none** of the
real, dispatchable registry. Asking "what can I do" through the purpose-built method
returns fiction.

### 2. The staged plan

`can_promote()` is a placeholder by its own module's admission
(`orchestration/CLAUDE.md`: *"evaluates a structural placeholder criterion ... rather
than real per-phase AcceptanceQuery objects"*) — any phase with one recorded op passes.

More importantly: **nothing exposes phase, promotion, or scene listing as an MCP tool.**
`inspect` role has zero tools; there is no `get_phase`, `list_objects`, or `promote`.
Confirmed live: calling `unwrap_uvs` (POLISH) and `add_railing` (REFINE) while
`app.orchestrator.phase` had never left `blockout` both succeeded silently — no warning:
`phase still: blockout` / `called POLISH tool while phase is blockout -> ok= True`.
`dispatch` checks only that the tool is visible to the `role` string the *caller* passes
per call; it never compares that to `self.phase`. Combined with Journey 1's fictional
`tools_for()`, an agent has no reliable way to learn what phase it's in or what promoting
needs — it can only guess, and any ordering is accepted.

### 3. Build a real thing

Built a 4m×4m room — floor, four walls, a door opening, a 12-tread staircase, a railing —
through `dispatch`, real Blender backend, one lease held throughout:

| Step | ms | Objects produced |
|---|---|---|
| add_floor | 3.4 | 1 |
| add_wall × 4 | 1.4–2.1 each | 4 |
| add_opening (2nd attempt) | 10.3 | 0 (modifies wall_n) |
| add_staircase (12 treads) | 12.8 | 12 |
| add_railing | 35.3–40.6 | 40 (5 posts, 34 balusters, 1 rail) |

Total: **58 objects**, ~69ms real compute. `build_app()` itself: 0.554s once.

Usable? Partially. The door boolean immediately left `wall_n` with **4 unresolved
`loose_or_duplicate` defects** ("vertex 19 duplicates vertex 13, not welded") — visible in
the next check-loop response, never auto-repaired. I then ran the pairwise check the
automatic loop does *not* run (Journey 4): 480 baluster/post × tread pairs, 14ms, **39
clipping defects** — all real socket joinery reported as bugs because nothing declared a
`JoineryIntent`. Same shape of finding as `docs/qa/report-1.md`'s B-00K (94 warnings on a
similar build), reproduced independently at 39/480 here. Dimensions all measured back
exactly as specified, but "manifold and meeting cleanly" is **no** without a manual,
tool-less follow-up.

### 4. The check loop

Response sizes for the same build (`len(json)/4`):

| Op | ~tokens | new_problems |
|---|---|---|
| add_floor | 134 | 0 |
| add_wall (×4) | 135 each | 0 |
| add_opening | 370 | 4 |
| add_staircase (12 treads) | 997 | 0 |
| add_railing (40 objects) | **3,398** | 0 |

**~5,400 tokens** total for one small room's check-loop output alone. `add_railing`'s
report (13,592 chars) lists dimensions + triangle_count per object individually with no
summarization; a `add_modular_kit`/`array_along` call at Gate A 11.4's "thousands" scale
would produce far more, every call, under the default `EVERY_GEOMETRY_CHANGE` cadence.

More consequential: `new_problems` is not what Gate A 3.1 implies. It calls
`measure.inspect(engine, obj)` per touched object, whose own docstring says it *"Excludes
the pairwise checks (find_clipping, find_visual_gaps), which need a second object."* So
"check after every geometry change" never checks whether the new thing clips its
neighbours — exactly what produced 39 undetected defects in Journey 3. Yet
`checks_scope: "changed+neighbours"` appears verbatim in every `ActionReport` (seen in
`add_floor`'s own response) — a label promising neighbour-checking the code doesn't do.

### 5. Something goes wrong

`make_plumb` on a nonexistent object raised cleanly (`align.unknown_object: object_id
'does_not_exist_object' does not exist`), but its `suggestion` field dumped **all 58 live
object ids** inline — recoverable here, but at thousands of objects (11.4's target) this
becomes unusable rather than a targeted hint.

Scene state was untouched by the failure (`objects identical: True`, `head unchanged:
True`). Real undo (add `temp_box`, `scene.undo(1)`) worked correctly:
`temp_box exists: False` after, object set restored exactly, `head` reverted — matching
the QA report's orphan-geometry fix.

### 6. The live view

Attached the viewer, drove ops, read `app.viewer.pending()` directly (no browser; ES
modules per the environment note). `translate.py::_translate` emits only 5 of the wire
protocol's 13 message types (`MESH_UPSERT`, `TRANSFORM_UPDATE`, `OBJECTS_REMOVED`,
`FULL_SCENE`, `PHASE`) — confirmed live, `add_primitive` queued exactly one `mesh_upsert`.

`frontend/src/main.js` fully handles `HIGHLIGHT`, `LOG`, `PROBLEMS`, `CONFLICT`,
`EXPORT_REPORT`, `RUN_STATE` — all dead in practice, since the backend never constructs
any of them. So Gate A 5.3's "latest change highlighted" shows **nothing**: the viewport
silently updates meshes with no cue which one changed, and the action log shows only
connection status and, if reached, phase lines. The highlight would not help find what
changed — it never arrives.

### 7. Export and hand off

Through `dispatch`, `export_scene` crashes (`KeyError`, Journey 1). Bypassing dispatch and
calling `export.export_scene()` directly, as `app_test.py`'s own test does, on the room's
floor+walls: `export took 0.052s`, `ok: True`, `banner: Exported .../room_roblox.glb for
roblox — 60 tris, clean.`, file exists at 6304 bytes, `defects: ()`. Fast, and the banner
genuinely tells a person it's safe to import. But it's reachable only by writing Python
that calls the module directly — not through any tool an MCP-connected agent, or the
product's own stdio/HTTP server, can invoke. The subscription-connected agent Gate A 7.4
asked for gets an internal `KeyError` the moment it tries to finish the job.

## The four questions, answered

- **Most confusing thing**: two disagreeing answers to "what can I do" —
  `mcp_server.registry` (real, 29 tools) vs. `orchestration.tools_for()` (fictional, 0 of
  16 names match a real operation) — plus role visibility fully decoupled from phase
  state, so no out-of-sequence call is ever refused or flagged.
- **Most steps that should be fewer**: an ambiguous scalar/vector parameter
  (`add_opening.position`) costs a wasted round-trip the schema alone can't prevent; more
  broadly, verifying a build for clipping requires the agent to hand-build its own O(n²)
  object-pair list, since no tool wraps `find_clipping` and the automatic loop skips it.
- **What a person would expect that doesn't exist**: a working `export` call through the
  agent's own tools; a way to ask "what phase / what's built / promote me"; the detail
  pass (Gate A 8.4's named first-class capability) reachable as a tool at all (0 of 3
  functions MCP-visible); a live view that shows what just changed.
- **Is Gate A 4.4 (fully autonomous) viable?** Not as built. An agent can build
  indefinitely — any role's tools succeed regardless of phase — but hits two dead ends: it
  can never call `promote` (not an MCP tool) and can never export (the one MCP tool
  crashes with an unhandled `KeyError`). A real `.glb` was reached only by stepping
  outside the agent's actual interface and calling the export module directly — precisely
  the manual intervention 4.4 said should never be necessary.

## Decisions for the user

- **`export_scene`/`check_export_budget` unreachable via the real agent path** — the
  terminal step of every journey raises an unhandled `KeyError`, not a `ToolError`.
  Options: (a) wire both into `app.handlers.build_handlers()` so `scene.apply` recognizes
  the kind — smallest, matches every other tool; (b) give their `ToolSpec.handler` a real
  callable so `dispatch` calls them directly, bypassing the log; (c) leave as-is. Recommend
  (a) — least special-cased, and the log already needs an export record for the action-log
  journey. Impact: no autonomous or MCP-driven run can finish without it. Evidence:
  Journeys 1 and 7, reproduced live.

- **Two disconnected tool catalogs, one fictional** — `orchestration._tool_registry`
  (used by `Orchestrator.tools_for`) lists 16 operation names absent from the real,
  dispatchable registry. Options: (a) delete it, have `tools_for` delegate to
  `mcp_server.registry.tools_for`; (b) rename its entries to match real operations so it's
  accurate if incomplete; (c) leave it — nothing live calls `tools_for` today, so the
  damage is confusion, not a runtime bug, yet. Recommend (a). Impact: low today, high the
  moment a phase-aware "what can I do" tool is built on top of it. Evidence: Journey 1,
  both files read directly.

- **The automatic check loop skips pairwise checks** — `_new_problems` calls
  `measure.inspect` only, which explicitly excludes `find_clipping`/`find_visual_gaps`,
  while `ActionReport.checks_scope` literally reads `"changed+neighbours"`. Options: (a)
  have `_new_problems` also run `find_clipping` against spatial neighbours
  (`src/spatial/index.py` already exists for this); (b) rename the field to stop promising
  neighbour-checking it doesn't do, and expose clipping as an explicit on-request tool;
  (c) leave as-is. Recommend (a) at small/medium scale with (b)'s honesty as the fallback
  once a full sweep gets too slow — but a choice is needed, since the field name actively
  misleads today. Impact: this is exactly how 39 real clipping defects went unflagged in
  one small room. Evidence: Journeys 3–4, 480-pair sweep run live in 14ms — cheap enough
  here that skipping it reads as an oversight, not a performance necessity.

- **Detail-pass and phase/status tools are not MCP-visible** — `detail` role has 0 tools
  (the module's 3 functions have real handlers, but `detail` publishes no `DETAIL_SPECS`,
  so the registry never sees them); no tool reads phase, lists objects, or promotes.
  Options: (a) publish `DETAIL_SPECS` (small, mirrors every other content module) and add
  a minimal `inspect`-role tool set plus a `promote_phase` tool; (b) accept detail passes
  as agent-inaccessible in practice; (c) leave as-is. Recommend (a) — the module is done
  and tested, only the registry step is missing. Impact: without it, no agent can reach
  phase 3 of the staged plan, or ever leave phase 1, through its own tools. Evidence:
  Journeys 1–2, registry dump showing `detail: 0`, `inspect: 0` live.

- **The live view emits 5 of 13 wire message types** — `HIGHLIGHT`, `LOG`, `PROBLEMS`,
  `CONFLICT`, `EXPORT_REPORT`, `RUN_STATE` are fully handled in `main.js` but never
  constructed by `viewer/translate.py`, which only sees raw `SceneChangeEvent`s, never
  `perform()`'s `ActionReport`. Options: (a) extend `_translate`/wire `perform()`'s report
  into the viewer to emit `HIGHLIGHT` after every mutating op and `LOG`/`PROBLEMS` from
  `new_problems`; (b) trim the frontend's dead branches to match current backend scope;
  (c) leave as-is. Recommend (a) for `HIGHLIGHT` specifically — Gate A 5.3 named it, and
  the frontend already renders it correctly. Impact: the live view's headline feature does
  nothing during a real run. Evidence: Journey 6, `_translate`'s 5 branches against
  `ServerMessageType`'s 13 members.
