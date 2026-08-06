# Review research — pass 1

Five read-only agents, none of which fixed anything. Two of them (`behaviour`, `experience`)
drove the real product against real Blender 5.2.0 LTS rather than reading it; `landscape`
re-checked the competitive field on 2026-08-06; `drift` walked all 48 Gate A decisions and
11 ADRs against the source; `debt` totalled the bill.

**The one-sentence version: almost everything works, and almost none of it is reachable.**

The engine is real. The measurement is real and correct — two 45°-yawed beams 1.4 m apart
measure 1.314 m, a post through a deck reports "inserted 0.5 m along z, 0.1 m to separate",
a railing on a 31.7° rake produces 16 posts whose local +Z equals world +Z to 1.000000.
Thirty of thirty-one operations produce correct, measured geometry. And then an agent
connected over MCP cannot call `measure` at all, cannot call `detail` at all, cannot ask
what phase it is in, cannot promote a phase, and crashes with a raw `KeyError` the moment it
tries to export.

## What exists — the honest version

A person or agent driving this can, **today, verified by running it**:

- **Build**: 6 primitive types, walls, floors, boolean openings, staircases, railings on
  sloped multi-segment paths, arrays along paths, LOD chains, modular kits. All dimensionally
  exact to the millimetre. 58 objects for a small room in ~69 ms of compute.
- **Repair**: 8 repair operations, each verified by re-running the detector that found the
  defect — 1→0 holes, 3→0 duplicate vertices, 1→0 flipped faces, 0.05 m gap → 0.000000 m.
  `split_non_manifold` is detect-only and says so.
- **Align**: 7 constraint-solver operations. 31° → 0.000000°, 50° → 90.000000°, a leaning
  post → exactly plumb. This is the one differentiator that is cleanly, fully achieved.
- **Detail**: bevel, panel lines, greebles — real geometry (12→88, 12→212, 12→24 triangles),
  manifold preserved in every case. Reachable only from Python, not from any tool.
- **Finish**: UV unwrap and PBR bake, writing real albedo/normal/roughness PNGs headless.
  Export for Roblox / Unity / Godot / Unreal producing valid `.glb` in under 0.06 s.
  Reachable only from Python, not from any tool.
- **Measure**: 4 metrics and 10 defect classes, each verified against a fixture built to
  have exactly that one defect. Reachable only from Python, not from any tool.

What it cannot do at all: generate a mesh from a prompt or an image; rig or sculpt anything
organic (zero code, not thin code); render anything for a vision model to critique.

## Intended vs actual — drift, worst first

`drift` classified all 48 gate decisions: **36 match, 2 drifted deliberately with a recorded
reason, 11 drifted with no record anywhere, 1 was decided and not built.**

| # | Decided | Built | Where |
|---|---|---|---|
| 1 | 1.2 "drops into a game engine" | `export_scene` is a registered MCP tool with no handler — `dispatch` raises `KeyError`. `app_test.py:66` carves it out of the very test built to catch this, with no comment | `src/app/handlers.py`, `src/app/app_test.py:66` |
| 2 | 3.2 + ADR-007: a phase hands off when its acceptance queries pass | `can_promote()` computes `len(produced_this_phase) > 0` — "did anything happen". `measure.evaluate` has zero non-test call sites | `src/orchestration/phases.py:34-58` |
| 3 | 5.1/5.3/5.4/3.1: live view, action log, cadence menu, pause/rollback/redirect | All built, all tested, all real — and `viewer.serve()` is never called by `forge3d serve`. No path from a running server to a browser exists | `src/forge3d_cli.py:79-104`, `src/viewer/server.py:66-88` |
| 4 | 8.4: the three detail passes, first-class | `detail` publishes no `*_SPECS`; the DETAIL role has 0 tools. So does INSPECT (10.1's "many readers") | `src/mcp_server/registry.py:35-41` |
| 5 | 6.1 + ADR-002: constraints stay live in a parametric file | `persistence.py` serialises 9 of `Operation`'s fields; `placements`, `joinery`, `acceptance` are dropped. Move a wall after a reload and the railing does not follow | `src/scene/persistence.py:67-92` |
| 6 | 4.2 verbatim "what rule it broke" | True for validation failures. False for geometry-helper failures — bare `ValueError`s from degenerate paths reach the agent as raw tracebacks | `src/app/handlers.py:152-162` |
| 7 | 3.1 "after every change that touches geometry" | It runs — but `_new_problems` calls `measure.inspect`, which by its own docstring excludes the pairwise checks. Every `ActionReport` still reads `checks_scope: "changed+neighbours"` | `src/orchestration/reporting.py` |
| 8 | 6.4 no built-in dimension table | `add_railing` defaults `post_size`/`baluster_size`/`rail_size` to 5 cm/5 cm/3 cm when omitted | `src/ops/railing.py:72-74` |
| 9 | 2.3 "attempt everything" | Rigging and organic sculpting: zero code. A-004 promised `docs/HANDOVER.md` would say so honestly; that file does not exist | repo-wide |

Deliberate and recorded: ADR-008 named three.js, a hand-written Canvas2D renderer shipped
instead (`frontend/README.md:52-68` — no network to fetch three.js); the MCP SDK server path
was left unverified on purpose (`src/mcp_server/CLAUDE.md`) — though `debt` found the SDK
*is* installed, so that reason is now stale.

## Where it falls short of the field

`landscape` re-checked on 2026-08-06. The original survey's "only unshipped papers do this"
framing is now **stale but not wrong-headed**: `blender-ai-mcp` (52★, Apache-2.0, CI) ships
live `scene_measure_distance` / `scene_assert_contact` / `scene_assert_dimensions` MCP tools
today, and NVIDIA shipped a CAD-to-SimReady Blender validation blueprint on 2026-07-20.
Neither is mature. `blender-mcp` (25.5k★) is unchanged and still has no measurement at all.

| Instead of this, pick… | …and you get | …and you give up | Cost to close |
|---|---|---|---|
| `blender-mcp` | 25.5k-star ecosystem, asset import, viewport screenshots, one-file install | constraint solver, write leases, checkpointed undo — but **not** measurement, since ours is unreachable too | n/a |
| `blender-ai-mcp` | working geometry assertions an agent can call **right now** | richer defect taxonomy, phase model — capabilities that exist here and cannot be called | small: publish `MEASURE_SPECS` |
| Meshy / Tripo | a textured mesh from a prompt in under a minute | dimensional precision, manifold guarantees | out of scope — no generative path here |
| Zoo / AdamCAD | B-rep solids, STEP, manufacturability | render-oriented output, architectural kit-of-parts | out of scope — no CAD kernel |

Differentiator scorecard: **1 achieved** (constraint-DSL placement), **4 correct but
unreachable** (spatial truth, JoineryIntent, bevel pass, the numeric replacement for
render→critique), **1 dead code** (programmatic definition-of-done), **1 correctly not
attempted** (safe execution — Gate A 7.2 chose unrestricted, and `raw/executor.py` delivers
exactly that, documented in `describe_risk()`).

## What surprised us

- **The default cadence costs 1000× more than the work it checks.** Creating a 960-triangle
  sphere: 0.006 s. `find_self_intersections` on it afterwards, automatically, finding zero
  defects: **6.5 s**. It is an O(triangles²) pure-Python sweep with no broadphase — while
  `src/spatial/` exists in this codebase for exactly that purpose and is not used by it.
  40% of a realistic 33 s session is this one check.
- **`undo` is session-fatal.** `scene.replay()` rebuilds the whole log from `engine.reset()`
  every time. One operation targeting an object the log did not create — which is the
  documented `reset_scene=False` "open an existing .blend" workflow — and every subsequent
  undo/redo/rollback raises `EngineError` forever.
- **Undo across a `raw_execute` barrier re-executes instead of restoring.** The snapshot is
  now captured (QA round 2) but nothing reads it back. A non-deterministic script produced
  1 object, then 3 differently-named objects after undo+redo — provably different geometry,
  while reporting `FULL_RESYNC`. `SECURITY.md`'s guarantee is still not true.
- **There are two tool registries and the one named `tools_for` is fiction.**
  `orchestration/_tool_registry.py` lists 16 operation names, **zero** of which exist in the
  real dispatchable registry. It is the method a phase-aware "what can I do now" query would
  call. Nothing in `src/app/` calls it.
- **The frontend handles 13 message types; the backend sends 5.** `HIGHLIGHT`, `LOG`,
  `PROBLEMS`, `CONFLICT`, `EXPORT_REPORT`, `RUN_STATE` are fully implemented in `main.js`
  and never constructed. Gate A 5.3's highlighted-latest-change shows nothing.
- **One small room produced 39 real clipping defects that the automatic loop never saw** —
  and finding them by hand took 14 ms across 480 pairs. The check is skipped for reasons
  that are not performance.
- **The codebase is unusually clean on the axes that usually rot**: no TODO/FIXME/HACK
  anywhere, no commented-out code, no scratch files, no file within half of its hard cap.

## The bill

- **10 assumptions**: 8 still true, **A-008 unverified** (1 Roblox stud = 0.28 m, carried
  with no citation, in the *primary* export profile the user named), **A-009 contradicted**
  (Puppeteer declared, not installed — nothing has ever run in a real browser).
- **Open backlog**: Q-017 (tests-first git evidence — 6 modules have no RED commit; QA
  declined to fabricate them), B-00K (railing declares no joinery → 94 clipping warnings),
  B-00L (real bevels give ~116 mean triangle aspect ratio). Plus B-029/030/031 deferred by
  design. 30 of 61 entries carry no `status` field at all; 24 of those are actually done.
- **Never run, by anything**: the MCP SDK server with a real client; the viewer socket with
  a real frame; a real browser; the engine subprocess fallback (an honest `raise`); **real
  OS concurrency on the write lock** — zero `threading.Thread` anywhere in the lock tests,
  for the guarantee the entire multi-agent design rests on; anything above ~900 objects
  against a stated target of thousands.
- **Duplication that has already drifted**: `sample_polyline` in `engine/_curve.py` lacks
  the `spacing <= 0` guard its twin in `testing/mesh_helpers.py` has — an infinite loop if
  called directly. Four copies of `_triangle_normal` still disagree on the degenerate return
  value. Two tool registries that cannot agree.
- **Stale docs**: `mcp_server/CLAUDE.md` + `README.md` describe the package collision as
  live and blocking when it is fixed, and claim the SDK is not installed when it is;
  `viewer/CLAUDE.md` says the same of `websockets`/`starlette`; `ARCHITECTURE.md` lists the
  subprocess fallback as working.
- **Seven files marginally over the 300-line soft cap** with no one-line justification, five
  of them in `contracts/` where splitting is explicitly disfavoured. A five-minute fix.

## Decisions for the user

Twenty-three candidate decisions came back. After the Phase 6 filter — drop anything Gate A
already settled unless the built product contradicts it, drop anything that could have been
asked at Gate A, drop anything already scheduled — **18 survive**, grouped into six Gate B
waves below. Full text and evidence in `.pipeline/question-backlog.json`, entries `R-001`
through `R-018`.

**There is exactly one build pass left.** That is the frame for every question here: not
"should this be right eventually" but "does this go in the last pass". The recommended
defaults below add up to roughly a full pass; anything added displaces something.

| Wave | Theme | Questions | Why it is a decision and not a fix |
|---|---|---|---|
| 1 | **Unreachable capability** | R-001 export, R-002 measure+detail tools, R-003 phase/inspect tools | *Which* of these gets wired, and how — handler vs `ToolSpec.handler`, and against ADR-003's 5–8-tools-per-role accuracy budget |
| 2 | **Verification that does not verify** | R-004 `can_promote`, R-005 pairwise checks skipped, R-006 JoineryIntent | Auto-declaring joinery lets an operation certify itself — the exact thing this product exists to refuse |
| 3 | **What the checks cost** | R-007 O(n²) sweep, R-008 report size | Prune, change the default cadence, or cap by triangle count — all defensible, different trade-offs |
| 4 | **Durability** | R-009 undo, R-010 raw barrier, R-011 reload drops constraints, R-012 browser unreachable | Fix vs constrain vs document; R-011 changes a persisted format, which gets harder the longer it waits |
| 5 | **What to prove vs what to build** | R-013 the four never-run paths, R-014 A-008 studs, R-015 error rules | The single highest-leverage call in this gate: one pass spent proving the multi-agent guarantee, or spent on features |
| 6 | **Cut list** | R-016 dead registry, R-017 subprocess flag, R-018 railing defaults + Q-017 + rigging/HANDOVER | Deleting is also a decision, and cheaper than the alternatives |

Dropped by the filter, recorded here instead of asked: routing `ops/` through
`constraints.solve` (two green implementations, no observed drift — leave until a bug
proves otherwise); benchmarking against `blender-ai-mcp` (real, but not a build-pass
decision — it goes to `HANDOVER.md`); the seven soft-cap files (one line each, no user
input needed).
