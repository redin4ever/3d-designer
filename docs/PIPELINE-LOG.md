# Pipeline log

What ran, what was decided, what was assumed, what is queued. This is the record the user
reads instead of having watched.

## Phase 0 — Bootstrap (2026-08-05)

**Ran:** created `.pipeline/`, `docs/{adr,decisions,research,qa}/`; installed all 6 rules
into `.claude/rules/` and both hooks into `.claude/hooks/` wired via `.claude/settings.json`
(`check-file-size.mjs` on PostToolUse, `pipeline-continue.mjs` on Stop); copied the gate
(`.pipeline/check.mjs` + `lib/`); seeded `CLAUDE.md`, `.gitignore`, `.claudeignore`,
`docs/ASSUMPTIONS.md`; `git init` + first commit.

**Idea as given:** a tool/app that lets AI models author 3D models live — assisting with
blank/gap filling, pushing design detail and realism beyond "stitched-together cubes",
handling angle adjustment and part clipping (e.g. railings), with multi-agent / sub-agent
task assignment, aimed at raising model accuracy, detail attention and spatial awareness.
Blender/`bpy` named as an acceptable starting point.

**Environment facts found:** Node v24.18.0 and git 2.55.0 present. Python **not** installed
(Store alias stub only). Blender **not** installed, not on PATH. Recorded in `CLAUDE.md`;
this is a hard constraint on how the product can be tested here.

**Decided:** nothing about the product. Phase 0 makes no design choices.

**Queued for Gate A:** nothing yet — Phase 1 populates the backlog.

**Repo now:** empty of source, fully instrumented, `state.json` at `phase: 1, pass: 1`.

## Phase 1 — Research (2026-08-05)

**Ran:** five concurrent read-and-report agents (`landscape`, `flows`, `domain`, `technical`,
`agent-ergonomics`), all synchronous. `inventory` was skipped — the repo had no source. The
fifth agent is not in the standard phase-1 set; it was added because the brief's actual thesis
("skyrocket the model's accuracy, detail attention and spatial awareness") is an agent-ergonomics
question, not a 3D one, and would otherwise have gone unresearched.

**Produced:** `docs/research/{landscape,flows,domain,technical,agent-ergonomics}.md` and
`docs/research/SUMMARY.md`. 50 raw "decisions for the user" deduped into 38 backlog questions
across 10 waves.

**The finding that reframed the product:** across seven independent spatial benchmarks (BLINK,
What'sUp, VSI-Bench, 3DSRBench, EmbSpatial, VisFactor, SpatialVLM), frontier VLMs score 34–56%
where humans score 79–99% — and the gap is worst on left/right, near/far, distance, occlusion and
viewpoint change, which is precisely what a 3D authoring loop asks of them. Every existing tool
hands the model a screenshot and asks it to place things by eye. That is the architecture, and it
is also why the output looks like glued boxes. The tool must compute the spatial facts.

**Other load-bearing findings:**
- No shipped product closes the render→critique→edit loop. It exists in BlenderAlchemy (ECCV'24),
  SceneCraft (ICML'24, +45.1%/+40.9% CLIP over one-shot) and LL3M (2025) — all papers.
- Raw coordinates vs constraints is measurable: SpatialVLM lands within 2× of truth 37% of the
  time; LayoutGPT/NSR-1K constraint+solver measures 91–95%.
- Agents falsely report success 13–89% of the time; LLM judges catch it at AUROC ≤0.65. So
  definition-of-done must be a re-run measurement, not a claim.
- Multi-agent: Anthropic +90.2% at ~15× tokens; Cognition's counter-case is specifically shared
  mutable state — which a live 3D scene is. Both converge on many readers, one writer.
- Tool-count optimum is K≈2.3–7.4 visible tools; RAG-MCP measured 13.62%→43.13% with retrieval.
- blender-mcp, the de-facto bridge, has an open CVSS 9.0 RCE (issue #304) via unsandboxed `exec()`.
- Bevel-every-plausible-edge is the most-cited realism lever but is practitioner consensus, not a
  measured study — and uniform beveling is itself an artificiality tell. Recorded honestly.

**Hard constraints found:** no Blender and no Python on this machine (`bpy` 5.2 needs exactly
Python 3.13, 338 MB wheel); `bpy` is GPL-3.0 with the `import`-into-your-process case genuinely
unsettled; Blender's Python API breaks between versions with no deprecation policy; many `bpy.ops`
operators fail headless on `poll()`; MCP `ImageContent` costs 15–25k tokens per image on clients
that mishandle it; non-convex mesh-mesh penetration depth is unsolved (FCL returns 0 on real
contact); no production-ready incremental glTF/USD streaming format exists.

**Decided:** nothing about the product. Phase 1 gathers and asks.

**Assumed:** nothing yet — no unknown forced a choice, because no code was written.

**Queued for Gate A:** 38 questions, `.pipeline/question-backlog.json`, waves 1–10.

**Repo now:** six research files under `docs/research/`, `CLAUDE.md` summary replaced,
`state.json` at `phase: 2`.

## Phase 2 — Design candidates (2026-08-05)

**Ran:** no `DESIGN.md` at root, no `--design` flag, no system named in the brief — so the
shortlist path. Register read as *dense professional tool with a live 3D canvas at its centre*,
watched by either a non-artist operator or a supervising artist.

**Fetched:** `linear.app` (safe), `figma` (contrast), `nvidia` (sharper). All HTTP 200, all parse
with `colors`/`typography`/`rounded`/`spacing`/`components`. Previews in
`.pipeline/design-candidates/previews.md`.

**One fetch rejected:** `runwayml` was the first "sharper" pick and returned 200 but ships prose
only — no YAML token frontmatter, so it could not generate a token file or be linted against.
Swapped for `nvidia`, which is also the better spread: linear and runway are both dark
cinematic-dev aesthetics, and a shortlist of three dark tools has one real option in it.

**Decided:** nothing. Phase 2 prepares; the user picks at Gate A. The wave message will say they
can name any of the other 71 slugs, supply a file or URL, or describe a brand to author from.

**Assumed:** nothing.

**Queued for Gate A:** wave 5 now carries the three previews plus density/motion/dark-mode/copy
personality. Q-017 ("is there a browser UI in v1 at all") is asked **first** in that wave — if the
answer is no, the design pick is moot and the wave collapses.

**Repo now:** three candidate files plus previews under `.pipeline/design-candidates/`,
`state.json` at `phase: 3`. No root `DESIGN.md` — correct; it is written only after the user picks.

## Phase 3 — Gate A (2026-08-05)

**Ran:** 12 waves, 48 decisions. Waves 1–10 from the backlog, then two follow-up waves on what
the answers opened up. Recorded verbatim in `docs/decisions/gate-A.md`.

**The four answers that shaped everything:**
- *"i will use this to make for example game designs"* — the use case. Engine-ready export,
  polygon budgets, LODs, modular pieces and axis/handedness conversion became first-class.
- *"make sure it supports my subscriptions eg: chatgpt subscription"* — forced MCP with both
  stdio and streamable-HTTP transports, since that is the only path a consumer subscription
  reaches the tool without per-token billing on top.
- Blender as the engine **plus** a full-toolchain test suite — a blocker, since neither existed.
  Resolved by asking; the user approved installing both.
- *"it should manage for all as i might use roblox's engine usually"* — four export profiles,
  Roblox primary. Roblox was not one of the offered options.

**Two answers were flagged as contradicting the research and stand as chosen.** 8.1 and 8.2 gave
verification to the agent's visual judgement and to a reviewing agent — the two options with
adverse published measurements (self-correction blind spot; false-success 13–89%; judges at AUROC
≤0.65). This was raised at the time and reconciled at 11.3 rather than overridden: measurement
decides hard facts (manifold, clipping, scale, transforms), the agent decides appearance. 7.2 and
7.4 chose unrestricted code execution and full disk access with the CVSS 9.0 precedent stated in
the option text; built as asked, documented in ADR-009 and `docs/SECURITY.md`.

**Toolchain installed and verified:** Blender **5.2.0 LTS** (build 2026-07-14), Python **3.13.14**,
and `bpy` **5.2.0** importing in-process (`import bpy` → live `bpy.data`). This last result decided
ADR-008 — the geometry core holds live Blender state rather than shelling out per operation.

**Design:** `linear.app` chosen from a shortlist of three. `runwayml` had been the first "sharper"
candidate and was rejected in Phase 2 for shipping no token frontmatter. Root `DESIGN.md` written.

**Recorded:** `docs/decisions/gate-A.md`; 10 ADRs (001–011, no 012); `docs/ASSUMPTIONS.md` with 10
entries decided without asking; `.pipeline/backlog.json` with 31 priority-ordered work items.

**Repo now:** `DESIGN.md` at root, decisions and ADRs written, `state.json` at `phase: 4, pass: 1`.

## Phase 4 — Build, pass 1 (2026-08-05) — IN PROGRESS

**4.1 Architecture, by panel.** Three architects worked independently on the gate decisions and
the backlog. Architect 3 won on one idea: **`EngineProtocol` frozen in contracts with a
`FakeEngine` injected at the composition root**, which makes every module except `engine` testable
with no Blender and turns `dependsOn` into an integration order rather than a build queue. Grafted
architect 1's split of `frontend` from `viewer` (different languages, different toolchains,
therefore different owners under Rule 5), and folded architect 1's thin `verify` module into
`orchestration`, which two of the three had independently placed there. Result: 16 modules,
`docs/ARCHITECTURE.md`, `.pipeline/modules.json`.

**4.2 Contracts frozen, then reviewed.** Wrote `src/contracts/` (10 files) plus `src/testing/`
(a real in-memory engine, not a call-recording mock — a mock lets a wrong implementation pass
because the test asserts on the conversation rather than the outcome).

Then the barrier. Two independent reviewers — a *consumer* who tried to express four gate journeys
using only these types, and an *adversary* who tried to reach states that must not exist —
returned **47 findings, 15 of them blockers**. Every one would have been multiplied by sixteen
modules. The most expensive:

- `AABB` could be constructed inverted, which short-circuits `overlaps()` to False on the first
  inverted axis — a *false negative* in the broad-phase test that feeds clipping detection.
- `MeshSnapshot` had no canonical edge ordering, but `bevel_edges` takes bare edge indices. A
  detail pass selecting "exposed convex edges" would have handed the engine integers meaning
  something else, and the wrong edges would have been bevelled with no error at all.
- `SceneDocument.head` could go negative, which slices from the end — an undo that silently drops
  the last operation instead of raising.
- An opaque (non-replayable) operation could exist with no undo barrier, letting rollback attempt
  a replay across code that cannot be replayed.
- Appending after an undo did not truncate, so a later redo would replay stale work ahead of the
  new operation.
- `WriteLease` was freely constructible, so "exactly one writer" — the safety property the whole
  multi-agent design rests on — was unenforceable. Two agents each holding a lease they built
  themselves is not a lock.
- `export_gltf` took only `y_up`, with no way to express `mirror_x` or `negate_rotation`. A
  left-handed target needs both together; the only remaining route would have been mutating live
  transforms before the call and reverting after.
- No `OperationHandler` protocol, so five separately-owned modules would each have invented a
  calling convention and `scene` would have needed five adapters.
- No path for a mid-run operator redirect to reach the agent at all.
- Three types defaulted three different tolerances for the same geometry, so one reading could be
  simultaneously "not a defect" and "acceptance-failing".

All fixed, each with a regression test named after the failure. 72 contract tests green.

**4.3 Ready queue.** Ten modules RED (601 failing tests, every failure `NotImplementedError`,
none `ImportError`). Two audit agents then asked the question that matters — *what wrong
implementation would still pass?* — and found six:

- `spatial.invalidate` could be a no-op, because every query re-read bounds anyway.
- `measure.gap_width` could simply delegate to `distance` (only the zero case was tested).
- `find_clipping` could apply any joinery intent globally instead of to the pair it names.
- `engine.reset` could clear a private ledger and never touch the live bpy scene, leaving
  Blender's default cube behind forever.
- `export_gltf` could drop the handedness flags and still write a valid file.
- `raw.execute` could text-scan the source instead of diffing real engine state.

Those gaps are now closed: spatial 15→18, measure 39→52, engine 25→54 conformance checks, raw
11→13. The engine suite runs the *same* check functions against both `FakeEngine` and real bpy, so
the fake cannot drift from the thing it stands in for.

**GREEN so far:** `spatial` (18), `measure` (52), `raw` (13), `constraints` (37) — 120 tests,
verified by running them, not by an agent's report.

**Still RED, awaiting implementers:** `engine`, `detail`, `ops`, `scene`, `export`,
`orchestration`. **Still planned:** `gaps`, `uv`, `align`, `viewer`, `mcp`, `frontend`.

**Assumed:** recorded per module in each agent's return and in `.pipeline/contract-requests.json`
(6 open requests, mostly `orchestration` needing `scene`'s real interface and a tool-registry
injection point).

**Repo now:** on branch `build/pass-1`, 10 commits, `state.json` at `phase: 4, pass: 1`.

### Phase 4 — Build, pass 1 — continued (2026-08-06)

**All 16 modules green**, plus a seventeenth the architecture panel did not foresee.

**The fan-out cost.** 3 architects, 2 contract reviewers, 10 test-writers, 2 test auditors,
16 implementers, 5 module reviewers (as a verified workflow), 1 completeness critic. One
implementer died mid-task on an API error and was retried per Rule 6 — the retry found a
real bug in the partial work it inherited (`matrix_world` stays stale after setting
location/rotation until `view_layer.update()`, which silently broke `world_bounds` after
any duplicate-then-move and would have fed stale cutter positions into every boolean).

**What the verification agents actually bought**, since a check that never changes an
outcome is a line item to delete:

- The **contract review** found 15 blockers before a single module was built against the
  frozen surface. Each would have been multiplied by sixteen.
- The **test audits** found six implementations that would have passed while doing nothing:
  `spatial.invalidate` as a no-op, `measure.gap_width` delegating to `distance`,
  `find_clipping` applying any joinery intent globally, `engine.reset` clearing a private
  ledger instead of the Blender scene, `export_gltf` dropping the handedness flags, and
  `raw.execute` text-scanning source instead of diffing state.
- The **engine retry** corrected a research assumption I had recorded as fact: `bpy` as a
  module *does* have window access in this build, so unwrap, bake and glTF export run
  in-process rather than needing the subprocess fallback. Also: Blender 5.2's boolean solver
  enum is `FLOAT/EXACT/MANIFOLD`, not `FAST`.

**The composition root.** There was no code anywhere that built an engine, a Scene, an
Orchestrator and the registry and wired them together — `pyproject.toml` declared a
`forge3d` entry point that did not exist. Rule 5 keeps every module out of its siblings,
which is what made parallel construction safe; the cost is that the wiring has to be done
once, deliberately, by whoever is allowed to know about all of them. `src/app/` is that,
and it found three defects no module suite could:

1. `ScenePort.document` declared a **method**; `Scene` exposes a **property**. Both
   consumers matched the declaration and both wrote doubles that matched it too, so three
   suites were green while the real trio could never have worked together.
2. `ops.validate_params` expected `Vec3`; an agent sends JSON lists. `ops` documented that
   conversion belongs at the boundary — correctly — and nobody built the boundary, so every
   point-taking operation raised `AttributeError` on first real agent contact.
3. `src/mcp/` shadowed the `mcp` PyPI SDK, so `import mcp` in our own transport resolved
   back to us and the SDK was unreachable. No subscription client could ever have
   connected, which is the one thing Gate A 7.4 asked for.

Also found and fixed: `ops`, `gaps` and `align` each correctly declared `ToolRole.REFINE`,
totalling 19 tools against a load-bearing 8-tool bound, with the registry's fair-cap
fallback silently hiding `repair`, `make_plumb` and `close_visual_gap`. Split into `REPAIR`
and `ALIGN` roles; every role now sits within 1–8 with nothing hidden.

**Verified, by running it:** 609 backend test functions, 54 engine conformance checks run
twice (fake and real Blender), 28 frontend tests. Both suites exit 0. `forge3d doctor`
exits 0 on Blender 5.2.0 LTS with all three optional dependencies present. The gate
(`node .pipeline/check.mjs --phase 4`) exits 0.

**The end-to-end proof**, on real Blender: a staircase and a railing come out of the real
stack; every railing post stands plumb on a 31° rake; a 30 mm interpenetration is detected
and a declared `JoineryIntent` silences it; the model exports for Roblox with the stud
conversion applied.

**Assumed:** recorded per module in each agent's return and in
`.pipeline/contract-requests.json`. The notable one: `orchestration` still cannot evaluate
real per-phase acceptance queries because it reaches `scene` through a `ScenePort` that now
exposes an engine but whose `can_promote` still uses a structural placeholder.

**Queued for Gate B:** `MetricKind` has no member for the realism proxies (`detail` and `uv`
both reuse unrelated kinds with the real name in `Measurement.detail`).

**Repo now:** branch `build/pass-1`, 15 commits, 17 modules green, `state.json` at
`phase: 4, pass: 1` pending the module-review workflow's verified findings.

---

## Phase 6 — Review research (pass 1)

Five read-only agents, none of which fixed anything. `behaviour` and `experience` drove the
real product against real Blender 5.2.0 LTS rather than reading it; `landscape` re-checked
the field on 2026-08-06; `drift` walked all 48 Gate A decisions and 11 ADRs against source;
`debt` totalled the bill. Briefs in `docs/research/review-1/`, synthesis in `SUMMARY.md`.

**What it found, in one sentence: almost everything works, and almost none of it is
reachable.** Thirty of thirty-one operations produce correct, measured geometry — a railing
on a 31.7° rake gives 16 posts plumb to 1.000000, two 45°-yawed beams 1.4 m apart measure
1.314 m, repairs are verified by re-running the detector that found the defect. And an agent
connected over MCP cannot call `measure` at all, cannot call `detail` at all, cannot ask what
phase it is in, cannot promote a phase, and crashes with a raw `KeyError` the moment it tries
to export.

Drift against Gate A: **36 match, 2 deliberate and recorded, 11 undocumented, 1 not built.**
The undocumented ones cluster: `export_scene` registered with no handler and carved out of
the one test built to catch that; `can_promote` checking that *anything happened* rather than
that acceptance queries pass, contradicting ADR-005 and ADR-007 with no superseding ADR; the
whole browser control surface built, tested and never started by `forge3d serve`; `INSPECT`
and `DETAIL` roles empty; save/load silently dropping every constraint, which is ADR-002's
entire stated payoff.

Three things nobody specified, found only by running it: the default check cadence costs
**6.5 s to find nothing on a sphere that took 0.006 s to create** (O(triangles²), while
`src/spatial/` exists unused for exactly this); `undo` is **session-fatal** once the log
touches an object it did not create, which is the documented `reset_scene=False` workflow;
and undo across a `raw_execute` barrier still **re-executes** rather than restoring — QA
round 2 fixed the capture half, not the read-back half, so `SECURITY.md`'s guarantee is
still untrue.

`landscape` corrected a stale premise honestly: the original survey's "only unshipped papers
do this" no longer holds — `blender-ai-mcp` (52★) ships live geometry assertions today and
NVIDIA shipped a Blender validation blueprint on 2026-07-20. Neither is mature, but a
52-star addon currently exposes more agent-callable measurement than this product does.

**Decided:** nothing. This phase observes and files; Gate B decides.

**Assumed:** nothing new. Two existing assumptions moved: **A-008** (1 stud = 0.28 m) is
still unverified and sits in the primary export profile; **A-009** is contradicted —
Puppeteer is declared but not installed, so nothing has ever run in a real browser.

**Queued for Gate B:** 23 candidate decisions came back; 18 survived the Phase 6 filter as
`R-001`–`R-018` in `.pipeline/question-backlog.json`, each with the evidence that raised it,
grouped into six waves: unreachable capability, verification that does not verify, what the
checks cost, durability, prove-vs-build, and the cut list. Dropped by the filter and
recorded instead of asked: routing `ops/` through `constraints.solve` (no observed drift),
benchmarking against `blender-ai-mcp` (real, but not a build-pass decision), and seven files
marginally over the soft cap (one line each, no user input needed).

**Repo now:** branch `build/pass-1`, 17 modules green, five review briefs and a synthesis on
disk, `state.json` at `phase: 7, pass: 1`. One build pass remains, which is the frame for
every Gate B question: not "should this be right eventually" but "does this go in the last
pass".

---

## Phase 8 — the final pass (pass 2)

Contracts reconciled first, in their own commit, before any module reopened: `RuleError` as
the one shape every named failure takes, `WriteLease.roles` + `PHASE_ROLES` + `PhaseViolation`
(ADR-013), `PhasePromotion.allow_override` deleted (ADR-012), `AcceptanceResult` gaining
subject/expected/suggested_operation, the three realism `MetricKind` members deferred twice,
`OperationResult.assumptions`, `ActionReport`'s summarisation fields, `SCHEMA_VERSION` 1→2
(ADR-015), and `ScenePort` moved into the frozen surface. All 8 open contract requests
reconciled — 7 resolved, 1 superseded.

**Round 1: six writers on disjoint paths, all landed.** The headline is F-003. The write
lock — the safety property the whole multi-agent design rests on — had never been tested
against real OS concurrency, and when it was, it was broken: eight threads racing behind a
barrier produced **three simultaneous holders of the "only" write lock**, because `acquire`
was an unsynchronised check-then-write. A second race made `find_conflicts` raise a bare
`KeyError` out of a read-only method, refusing 168 readers in one run. Both fixed, both
pinned by tests using real threads and barriers rather than sleeps.

Also in round 1: measure and detail published 10 MCP tools between them (INSPECT went 0→9);
session tools landed so an agent can orient and finish; export runs through its handler
outside the log; `can_promote` evaluates real acceptance queries with no override; undo
restores from a geometry snapshot instead of re-running raw scripts; schema v2 keeps
constraints across a reload; the automatic check finally checks neighbours;
`find_self_intersections` went 6.59s → 0.021s on a 960-triangle sphere (306×); bevel mean
aspect ratio 109.31 → 64.20, still manifold. **A-008 closed as verified** — 1 stud = 0.28 m,
per Roblox's own units table, corroborated exactly by its mass row.

**Round 2 was stopped by the user partway through.** Four units never ran (`mcp-live`,
`geometry-consistency`, and the second halves of `engine` and `viewer`). Two were
half-applied and reconciled explicitly per Rule 6 rather than left: `engine` was finished by
hand (F-023 — `prefer_subprocess` deleted, `ARCHITECTURE.md` and `engine/README.md`
corrected), and `viewer` was **reverted** to the last green commit rather than shipped with
11 failing tests and a partially rewritten bridge. `ops` and `frontend` had completed before
the stop and were kept.

**Decided:** to revert rather than finish the viewer unit. A half-written module compiles
about half the time, which is worse than it not existing, and there was no one left to catch
the regression.

**Assumed:** nothing new.

**Queued:** everything round 2 did not reach is written into `docs/HANDOVER.md`,
priority-ordered, with repros. The top item is that the installed MCP SDK is 2.0.0 while
`transports._build_server` is written against the 1.x decorator API — found and honestly
filed by the round-1 agent rather than hidden — so no live client can connect today even
though everything behind the transport is verified working.

**Repo now:** branch `build/pass-1`, 901 backend tests and 31 frontend tests green, doctor
exit 0 with 43 tools across 9 roles, `docs/PIPELINE-SUMMARY.md` written, `state.json` at
`status: finished`.
