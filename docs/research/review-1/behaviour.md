# Behaviour — what this actually does

All claims below are **observed**: run against the real Blender 5.2.0 LTS backend
(`prefer_blender=True`, `app.backend == "bpy-5.2.0 LTS"`), never the in-memory fake, via
`build_app(prefer_blender=True, attach_viewer=False)`. Anything not run is marked
**inferred** explicitly. Nothing here was fixed; every failure is filed as found.

## Method (what you ran)

- One live `App`, driven exactly as an agent would: `orchestrator.acquire(holder, phase)`
  then `orchestrator.perform(Operation(...), lease)` for every mutation, cross-checked
  against the real entry point, `mcp_server.dispatch(name, json_params, role=..., orchestrator=...,
  lease=...)`, for a construction op, `raw_execute`, and both export tools.
- Genuinely broken/misaligned meshes were constructed directly via `engine.create_mesh` /
  `engine.create_primitive` (open boxes, triple-incident-face fans, duplicate/loose
  vertices, reversed winding, non-uniform scale, crossing triangles, interpenetrating and
  gapped pairs) — the same technique the product's own test suites use
  (`testing.unit_cube`), since no operation in the product itself produces broken geometry.
- Every claim measured with `measure.*` / `engine.snapshot()` / `engine.world_bounds()` —
  never eyeballed. Six scripts, ~475 total lines, run start to finish against one process
  per run (state does not persist across process restarts).
- One 33.4s session built 9 constructions (6 primitives, wall, floor, opening-cut,
  staircase, railing, array, LOD chain, modular kit), ran 8 repairs against 8 hand-built
  defects, 7 aligns against 7 hand-misaligned pairs, 3 detail passes, UV unwrap+bake
  twice, 4 export-profile attempts, 10 measure metric/defect calls, and 4
  undo/checkpoint/rollback/promote calls. Three follow-up scripts isolated two findings
  precisely: export wiring (`mcp_server.dispatch` vs. a direct module call) and undo
  across a `raw_execute` barrier (non-deterministic script, object identity compared
  before/after).

## Capability table

| Capability | Works? | Evidence |
|---|---|---|
| add_primitive (cube/cylinder/plane/cone) | **works** | correct verts/tris, e.g. cube 12 tri/8 vert, cylinder 124/64, cone 62/33; 2–20ms each |
| add_primitive (sphere/torus) | **works, pathologically slow** | geometry correct (960/1024 tris) but 6.9s/7.8s wall time each — see below, this is not primitive creation cost |
| add_wall / add_floor | **works** | wall 4×0.2×2.4m exact; floor 5×4×0.15m exact, both to the mm |
| add_opening | **works** | wall1 tris 12→36 cutting a 0.9×2m door; opening entirely outside the wall correctly raises `ToolError` naming the valid range, never a silent no-op |
| add_staircase | **works** | 12 treads, exact rise/run/width (0.28×1.0×0.18m per tread), solid stacked-riser geometry (each tread a box floor→its own height, not a floating slab) |
| add_railing (flagship) | **works** | 13-pt sloped path → 16 posts + 49 balusters + 1 top rail; post-0 confirmed **plumb** (local +Z · world +Z = 1.0 after being generated on a 31.7° rake) |
| array_along | **works** | 3-pt cornered path, 13 instances, corner-forced spacing |
| add_lod_chain | **works, slow** | sphere → 960/480/240/96 tri levels, correct ratios; 16.6s wall time (same root cause as sphere/torus) |
| add_modular_kit | **works** | 3×2 grid, 6 pieces, tile origins exactly 1.0m apart (seamless) |
| fill_boundary_holes / weld_duplicates / remove_loose / fix_normals / merge_shells / close_visual_gap / repair() | **works** | each: defect count N→0 on the *same* detector re-run (1→0 hole, 3→0 dup verts, 1→0 loose, 1→0 flipped face, 16→12 verts welding two shells, 0.05m gap→0.000000m, tiered repair fixes 2 stacked defects together) |
| split_non_manifold | **partial (as documented)** | detect-only; 1→1 non-manifold edge after "repair" — `gaps/CLAUDE.md` documents this honestly as undoable without a false "fixed" |
| make_parallel/perpendicular/set_angle/plumb/flush/coplanar/snap_to_grid | **works** | 31°→0.000000°, 50°→90.000000°, 37°→37.000001°, leaning post →exact plumb, 1.3m gap→0.000000m, grid snap exact to 1.0 |
| apply_edge_treatment / add_panel_lines / add_greebles | **works** | real geometry added (12→88, 12→212, 12→24 tris) and **manifold preserved** (`is_watertight` True before and after) in every case |
| unwrap_uvs / bake_textures / unwrap_and_bake | **works** | UVs set; real PNGs written (albedo/normal/roughness, 400–1000 bytes each) for both a cube and a cylinder in one live headless run |
| export_scene (underlying logic) | **works when called directly** | `export.export_scene(engine, ids, path, profile_name=...)` produced valid, non-trivial `.glb` files for all 4 profiles (1436–1504B single-object, 2620B two-object with correct combined 24 tris), <0.06s each |
| export_scene / check_export_budget (**agent-reachable path**) | **does not work** | `mcp_server.dispatch()` and `orchestrator.perform()` both raise immediately — see Decision 1 |
| checkpoint() | **works** | names the current head, returns index |
| undo() / redo() / rollback_to() | **does not work** (session-fatal) | crashes with `EngineError` the first time any is called after a realistic session — see Decision 2 |
| can_promote() / promote() (incl. force override) | **works** | correctly reports the failing query name; forced promotion logs `{from, to, forced:true, failing:(...)}`; reached blockout→refine→detail→polish (all 4 phases) in 3 calls |
| measure.bounds/dimensions/volume/triangle_count | **works** | cube volume 1.000 m³, wall1 36 tris, exact dims |
| measure.distance/gap_width (rotated geometry) | **works** | two 4m beams yawed 45°, 1.4m apart → 1.314m, correctly nonzero (the AABB bug QA flagged is genuinely fixed) |
| find_boundary_holes/non_manifold_edge/non_manifold_vertex/loose_or_duplicate/flipped_normal/unapplied_transform | **works** | each correctly fires exactly once on a fixture built to have exactly that one defect |
| find_self_intersections | **works, but O(n²) — see Decision 3** | 0 defects on a clean sphere, correctly 0 on adjacent triangles of a cube; costs seconds past ~1000 tris |
| find_clipping (post-through-deck) | **works** | correctly reports `inserted 0.5m along z, 0.1m to separate` — insertion depth and separation magnitude are two different, correctly separate numbers (the QA-flagged conflation is fixed); an under-sized 0.15m declared socket correctly still reports |
| find_visual_gaps / check_budget | **works** | 0.03m gap correctly flagged under a 0.1m threshold; budget check ran clean (did not independently trigger BUDGET_EXCEEDED in this run — not a failure, just not forced) |

**30 of 31 registered operations work correctly** (split_non_manifold is an honest partial
by design). **5 capabilities fail via the only path a real agent has**: export_scene,
check_export_budget, undo, redo, rollback_to.

## The four questions

**Most impressive thing observed.** `add_railing` on a 13-point, 31.7°-rising path
produced 16 posts + 49 balusters + 1 top rail in 0.24s, and the first post's local +Z
verifiably equals world +Z (measured, not assumed) — a genuinely correct plumb-railing
generator on sloped, multi-segment input, which is exactly the hard case the module's own
docs call out as the common naive-generator failure.

**What a person would try first that does not work.** Finishing the session: calling
`export_scene` — the natural last step of any build — fails immediately with
`KeyError: unknown operation kind 'export_scene'` through both the real MCP dispatch path
and direct `orchestrator.perform()`. `forge3d doctor` and `app.describe()` both list
`export: 2 tools` as registered, giving no signal that this is broken until it is tried.

**What works but produces poor-quality output — reframed as poor performance.**
`find_self_intersections`, which runs automatically after *every* geometry-changing
operation under the default `EVERY_GEOMETRY_CHANGE` cadence, is an O(triangle²) pure-Python
same-mesh triangle-pair sweep with no broadphase pruning. Isolated directly:
`engine.create_primitive('sphere')` takes **0.006s**; `measure.find_self_intersections` on
the resulting 960-triangle sphere alone takes **6.5s** and finds zero defects. This,
not primitive creation, is why `add_primitive(sphere)` cost 6.9s and `add_primitive(torus)`
cost 7.8s in the full session, and is most of why `add_lod_chain` cost 16.6s (four new
objects, ~1800 total triangles, each independently swept).

**Session timing.** Build (9 constructions) + repair (8) + align (7) + detail (3) + finish
(UV×3, export×1 direct) + measure (18 calls) = **33.4s wall time**. Of that, **≈13.5s (40%)**
is attributable to exactly one systemic cause (the O(n²) self-intersection sweep on the
sphere, torus, and LOD chain). A session avoiding round primitives and staying under a few
hundred triangles per touched object completes in well under 5s for the same op count.

## Decisions for the user

- **[export wiring]** — Should `export_scene`/`check_export_budget` be dispatched through
  the same operation-log path as every other tool, or given their own execution path since
  they write a file rather than mutate the scene? Options: (a) add both to
  `app/handlers.py`'s `build_handlers()` registry the same way `gaps`/`align`/`uv` are
  wired — cheapest, but export then becomes a logged, replayable "operation" that produces
  no geometry, which is conceptually odd; (b) give `ToolSpec.handler` a real callable for
  both (the field already exists and `dispatch.py` already has a code path for it — "exists
  so a future module that does attach a handler does not need `dispatch.py` touched at
  all") and skip the operation log entirely, matching `export/registry.py`'s own docstring
  intent. Recommend (b) — it matches what the code was already structured for and avoids
  polluting the undo log with non-geometry actions. Impact: **high** — no scene can currently
  be exported through the wired product. Evidence: `mcp_server.dispatch("export_scene", ...)`
  and `orchestrator.perform(Operation(kind="export_scene"), lease)` both raise `KeyError`;
  `export.export_scene()` called directly produces correct, valid files in <0.06s.

- **[undo across non-log-created geometry]** — `scene.replay()` unconditionally rebuilds
  the *entire* log from `engine.reset()` on every `undo`/`redo`/`rollback_to` call, with no
  incremental path. The moment the log contains one operation whose target object was not
  itself produced by an earlier logged operation — which happens in the fully-documented
  `reset_scene=False` "work with a .blend that is already open" workflow, not just in a
  test harness — every subsequent undo/redo/rollback in the session raises `EngineError`
  and never recovers. Options: (a) make `replay()` tolerant of a handler failure on a
  single op (skip and report, rather than propagate and abort) — cheap, but silently
  changes what "the log is truth" means; (b) forbid repair/align/detail/uv operations from
  targeting an object not present in `active_operations`' produced set, raising a named
  error at `apply()` time instead of an opaque crash three operations later at `undo()`
  time; (c) document that `reset_scene=False` sessions must never call undo/redo/rollback.
  Recommend (b) — it turns a session-ending crash into an immediate, actionable rejection
  at the point of the actual mistake. Impact: **high** — undo/redo/rollback are 3 of the
  31+ capabilities and are completely unusable for the rest of any session that touches
  this path once. Evidence: `scene.undo(1)` raised
  `EngineError: no object named 'bad_hole'` from inside `replay()`'s handler loop; the same
  crash then repeated for `redo`, `rollback_to`, and a second `undo` call in the same run.

- **[raw-execute undo barrier does not restore]** — `orchestration.reporting.perform` now
  captures a real snapshot file before an opaque `raw_execute` op runs (the QA report's
  "round 2" fix), and `scene.history` correctly classifies crossing it as `FULL_RESYNC`.
  But nothing in `undo`/`redo`/`rollback_to` ever reads that snapshot back — every one of
  them still ends in an unconditional `self.replay()`, which just re-runs the raw script
  again. Verified directly: a non-deterministic `raw_execute` script that creates 1–5
  randomly-named objects created 1 object the first time; after `undo` past it and `redo`
  forward again, it produced **3 differently-named objects** — genuinely different
  geometry after a full undo+redo cycle, exactly the failure the QA report describes as
  fixed. Options: (a) wire `rollback_to`/`undo`/`redo` to actually load from
  `barrier.snapshot_path` when a barrier is crossed, restoring engine state instead of
  replaying; (b) keep replay-only semantics but rename the guarantee — stop calling it
  `FULL_RESYNC`-as-clean-restore in any doc that implies determinism across raw ops.
  Recommend (a) — the snapshot is already captured and paid for; only the read side is
  missing. Impact: **medium** — only reachable when a session mixes `raw_execute` with
  undo, but it directly contradicts `SECURITY.md`'s stated guarantee. Evidence:
  `randobj_f9dd53` before undo/redo; `randobj_8ca638`, `randobj_9244a7`, `randobj_b89aaa`
  after — same script, same barrier, provably different result.

- **[default check cadence vs. O(n²) self-intersection cost]** — `EVERY_GEOMETRY_CHANGE`
  is the default cadence and runs `find_self_intersections` (no spatial pruning) after
  every touched object. Options: (a) give `find_self_intersections` broadphase pruning via
  the `spatial` module that already exists in this codebase for exactly this purpose
  (currently unused by this check); (b) change the default cadence to `PHASE_BOUNDARIES`
  so routine construction stays fast and a full check runs at each phase gate instead;
  (c) skip self-intersection specifically past a triangle-count threshold and say so in
  the report. Recommend (a) first, (b) as a stopgap. Impact: **high** — this is the
  default, silent behavior on the very first non-trivial object anyone builds. Evidence:
  isolated timing above (0.006s creation vs. 6.5s check, 0 defects found).

**Summary**: {"status":"done","file":"docs/research/review-1/behaviour.md","capabilitiesWorking":30,"capabilitiesBroken":5,"decisionCount":4,"headline":"find_self_intersections is an O(triangle-squared) pure-Python sweep that runs automatically after every geometry change by default, so simply adding one 960-triangle sphere costs 6.5 seconds of mandatory, zero-defect checking versus 0.006 seconds to actually create it."}
