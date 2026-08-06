# Landscape — the built product against the field

## Method (what you searched and ran, dates)

Web research: ~20 queries, 2026-08-06 (the original survey is dated 2026-08-05 — barely a
day apart on the calendar, but the sources returned span January–July 2026, so the field
moved without the calendar doing so; dates below are each source's own). Fetched:
`github.com/ahujasid/blender-mcp` (README + issues), `github.com/PatrykIti/blender-ai-mcp`
(README + repo metrics), NVIDIA/Meshy/Zoo press coverage, arXiv abstracts for VIGA and
BlenderBench, Infinigen and AdamCAD release pages.

Code and product: read `README.md`, all of `docs/qa/report-1.md`, and — beyond what QA
covered — the actual source of `measure/`, `detail/`, `constraints/`, `raw/`, `ops/`,
`mcp_server/`, `orchestration/reporting.py`, and `contracts/operations.py`, plus every
module's `CLAUDE.md`. **Ran the product against real Blender** (`bpy-5.2.0 LTS`, confirmed
via `doctor`): built a live `App` via `build_app()`, acquired a write lease, performed
`add_primitive` twice to create an overlapping post/deck pair, ran `make_plumb`, called
`measure.report`/`measure.find_clipping`/`detail.select_bevel_edges`/`ops.acceptance_for`
directly, and dumped the live MCP tool registry role-by-role. Also ran
`pytest src/raw src/measure src/detail src/constraints src/align -q` (all green) and
`pytest src/app -q` (33/33). Full probe script:
`C:\Users\dafg\AppData\Local\Temp\claude\...\scratchpad\probe.py`.

## Has the gap closed? (the render-critique-edit loop, re-checked)

**Narrowing, not closed — and the honest headline is not about the field, it's about this
product.**

The flagship bridge, `ahujasid/blender-mcp` (25.5k stars), is unchanged: current README
still warns `execute_blender_code` is unsandboxed ("ALWAYS save your work before using
it"), has no measurement/verification tools, and issue #207 ("execute_blender_code enables
unrestricted arbitrary code execution") is still open. **Observed**, checked 2026-08-06.

Four things have shipped since the original survey that each close a sliver of the gap:
- **blender-ai-mcp** (`github.com/PatrykIti/blender-ai-mcp`, 52 stars, Apache-2.0, CI +
  tests) is a real, installable, maintained MCP server exposing `scene_measure_distance`,
  `scene_assert_contact`, `scene_assert_dimensions`, `scene_assert_containment` as live
  tools, plus a staged (LLM-orchestrated, not autonomous) vision-checkpoint loop
  (`reference_iterate_stage_checkpoint`). **Observed**, checked 2026-08-06.
- **NVIDIA Omniverse Agent Toolkit** + the **"SimReady" Blender** blueprint (SIGGRAPH 2026,
  announced 2026-07-20, `nvidianews.nvidia.com`) ships `ovphysx` and CAD-to-SimReady
  libraries giving agents physics validation and asset-validation skills inside Blender,
  openly available. Scoped to simulation-readiness, not general artistic critique, and it's
  a vendor blueprint, not a one-click product. **Observed.**
- **Meshy 3D Agent Beta** (launched 2026-06-04, `prnewswire.com`) is a shipped, commercial
  conversational "chat-to-3D" workflow. It is still generative-mesh underneath — nothing
  found indicates it fixed Meshy's own previously-admitted topology/UV/scale gaps; treat as
  an agentic UI wrapper, not a verification breakthrough. **Inferred**, not verified
  first-hand (closed product).
- **VIGA** (arXiv 2601.11109, 2026-01-16) formalizes a code-render-inspect loop with
  released code (`github.com/Fugtemypt123/VIGA`) and **BlenderBench** now exists as a
  matching benchmark — still a research artifact, not a maintained product with an install
  path a team would put in production. **Observed.**

So the "papers only" framing is stale — there is now at least one small real open-source
tool and one major-vendor blueprint doing pieces of this. None is mature or widely adopted.

**But the sharper finding is internal.** Running this product against real Blender and
reading `orchestration/reporting.py` end to end shows its own verification engine is barely
more reachable than what it is being compared against. `measure` (distance, gap, angle,
clipping, full defect report) and `detail` (the bevel pass) publish **zero MCP tool specs**
— confirmed by dumping the live registry: `detail: []`, and the role meant for measurement
tools (`inspect`) is also `[]`. A connected agent today gets dimensions/triangle-count of
whatever it just touched, plus seven classes of single-object topology defects, automatically
— and nothing else. **A 52-star third-party addon currently exposes more live,
agent-callable geometry-assertion tools than this product does.** Detail below.

## Side by side (table: competitor | what they do better | what we do better)

| Bucket / competitor | What they do better | What we do better |
|---|---|---|
| **blender-mcp** (ahujasid, 25.5k★) | Massive ecosystem, viewport-screenshot vision tool, Poly Haven/Sketchfab/Hyper3D import, huge community, works today with a one-file addon | Constraint-solver alignment (7 live tools, quaternion-composed — no gimbal drift), phase-locked multi-agent write leases, checkpointed undo, 4-engine export with audited axis/handedness — none of which blender-mcp has at all |
| **blender-ai-mcp** (PatrykIti, 52★) | **Ships live `scene_measure_distance`/`scene_assert_contact`/`scene_assert_dimensions` MCP tools today** — an agent can call them right now | Deeper measurement semantics under the hood (10 defect classes, JoineryIntent insertion-depth-along-declared-axis vs. their simpler contact/bbox model) — *but ours are not wired to any tool*, so on live reachability this line currently favors them |
| **Meshy / Tripo / Rodin / Meshy 3D Agent** | Generate a mesh from text or an image in seconds; PBR texture bake; Meshy's Agent Beta wraps this in a conversational multi-turn UI | Real dimensional control, manifold/repair guarantees, no per-generation credit cost — but this product cannot generate a novel mesh from a prompt at all; it only constructs from primitives/kits |
| **Zoo/KittyCAD Text-to-CAD, AdamCAD** (YC W25, $4.1M, 1M+ models by 2026-05-24) | Real B-rep solids, STEP export, manufacturability guarantees | Realistic-render-oriented output, architectural kit-of-parts (stairs/railings/walls) that CAD tools don't model natively |
| **Infinigen** (Princeton, BSD-3, v1.4.0 Indoors) | Photoreal terrain/plant/creature generation at a scale and diversity nothing here attempts | Prompt-driven and interactive; Infinigen needs a procedural-generation expert, not an agent conversation |
| **trimesh / PyMeshLab / Open3D / Meshmixer** | Mature, ubiquitous, battle-tested topology repair; no wiring gap — you call the function and get the answer | The `repair` role *is* live here (8 tools) and JoineryIntent is a genuinely novel idea none of them have — but see above: the idea is unwired to any tool that could use it |

## The differentiators, checked one by one (achieved / partial / not attempted)

1. **Render→critique→edit loop — PARTIAL (redesigned, then incompletely wired).** No code
   anywhere in `src/` renders a view and sends it to a vision model for critique (confirmed
   by search and by reading `mcp_server/images.py`, which only downscales an
   already-rendered image for token cost). This is a deliberate redesign, consistent with
   the project's own research: verification is numeric, not visual. But the numeric
   replacement is itself only partially delivered — see #2.

2. **Tool-computed spatial truth — PARTIAL.** `measure.report`/`find_clipping` are
   correct: probed live against real Blender, a post embedded in a deck reported
   `"inserted 0.1m along x, 0.1m to separate"` with a suggestion naming the exact
   `JoineryIntent` to declare, and declaring one (`depth=0.15`) correctly silenced it.
   **But `measure` publishes no `MEASURE_SPECS`, so it has zero MCP tool exposure** —
   confirmed via a live registry dump. No connected agent can request a distance, gap,
   angle, or clipping check, or a full defect report. `Orchestrator._new_problems` (the
   automatic post-op check) calls `measure.inspect`, which its own docstring says
   **"excludes the pairwise checks... which need a second object"** — so even the
   automatic path never surfaces the exact "railing clips the tread" scenario the README
   uses as its headline example.

3. **Constraint-DSL placement + solver — ACHIEVED.** The `align` role's 7 tools
   (`make_plumb`, `make_flush`, `snap_to_grid`, ...) are live in the registry and run
   through `constraints.solve`/`graph`/`anchors`. Confirmed working: `make_plumb` executed
   successfully against real Blender in the probe. Caveat: `ops/railing.py` and siblings do
   **not** call into `constraints` themselves (confirmed: zero non-`align` imports of
   `constraints` anywhere in `src/`) — they hand-roll equivalent placement logic directly,
   which is a documented, accepted implementation choice (`ops/CLAUDE.md`), not a defect.

4. **Semantic intersection model (JoineryIntent) — PARTIAL, effectively unreachable.**
   The type and its tolerance/axis logic are correct in isolation (verified above). But no
   tool's `input_schema` anywhere exposes a `joinery` parameter (confirmed: zero matches
   for `joinery`/`JoineryIntent` across `ops/`, `app/handlers.py`, `mcp_server/`), and the
   only consumer, `measure`, has no tool at all. An agent has no way — automatic or
   manual — to declare intent or trigger a clipping check today. This is the direct cause
   of QA's own open finding **B-00K** (a railing reports 94 clipping warnings because
   nothing ever produces a `JoineryIntent` for the sockets it deliberately creates).

5. **Programmatic definition-of-done — NOT ACHIEVED (dead code).** `AcceptanceQuery` and
   `measure.evaluate()` are implemented and correct (`acceptance_for("add_primitive", ...)`
   returns a real, well-formed query in the probe). But a full-repo grep finds **zero
   non-test call sites** for `measure.evaluate` and **zero non-test reads** of
   `Operation.acceptance` anywhere, including in `Orchestrator.perform()` — the one path
   every mutation takes (`orchestration/reporting.py`, read in full: it calls `_measure`
   and `_new_problems`, never `evaluate`). No operation's success is machine-verified
   against its own declared acceptance query in the live product today, contradicting the
   README's own claim: *"a task is done when the query that defined it comes back clean —
   never because an agent said so."*

6. **Heuristic bevel pass — PARTIAL, unreachable.** `select_bevel_edges`/`bevel_width_for`
   work correctly against real geometry (probed: 8 edges selected, 0.01m width computed on
   a 0.2×0.2×3m beam). `detail` publishes no `DETAIL_SPECS` and nothing outside `detail/`
   itself imports it (confirmed by grep) — zero MCP exposure, zero call from any
   construction op. QA's own **B-00L** (poor bevel topology, aspect ratio ~116) was found
   the same way I found this: by calling the function directly, not through the product.

7. **Safe execution — deliberately not attempted, confirmed accurate.** `raw/executor.py`
   is fully implemented (not the stub an earlier pass of this review's own research agent
   mistakenly reported — the file was read in full and is complete, tested, green).
   `describe_risk()` states the exposure plainly in-product; `README.md`/`SECURITY.md`
   repeat it. This matches Gate A 7.2 exactly — a decision, not a gap.

**Score: 1 achieved, 4 partial-but-correct-and-unreachable, 1 not achieved (dead code), 1
correctly not attempted by design.**

## What is obviously missing

**Pick blender-mcp instead** and you get: a 25.5k-star community, Poly Haven/Sketchfab
asset import, a viewport-screenshot vision tool, and a system that works the moment you
install one addon. You give up the constraint solver, phase-locked multi-agent safety, and
checkpointed undo — but you would *not* actually give up much on the measurement front,
because as shown above this product's own measurement engine is not reachable by an agent
either, today.

**Pick blender-ai-mcp instead** and you get working `scene_assert_contact`/
`scene_measure_distance` tools *right now*, on a smaller but real open-source project. You
give up this product's richer defect taxonomy and multi-agent phase model — capabilities
that exist in this codebase but that you, as an agent, cannot currently call.

**Pick Meshy or Tripo instead** and you get a mesh from a text prompt or a photo in under a
minute, with baked PBR textures, no Blender/Python-3.13 install, and no requirement to
place every primitive by hand. You give up manifold guarantees, dimensional precision, and
multi-engine export — this product cannot generate a novel mesh from a prompt at all; it
only constructs from primitives, walls, kits, and known architectural patterns.

**Pick Zoo/KittyCAD or AdamCAD instead** and you get real B-rep solids and STEP export —
manufacturable output. This product has no CAD kernel and makes no manufacturability claim.

## Honest positioning

This product is a precise, multi-agent-safe **construction** toolkit for Blender —
better than blender-mcp specifically at concurrent-agent safety, quaternion-stable
alignment, and audited multi-engine export, and better than every generative-mesh vendor at
dimensional control for the narrow set of things it knows how to build (stairs, railings,
walls, modular kits). It is not yet, as shipped, what its own README claims it is: the
verification and definition-of-done machinery that would justify "never because an agent
said so" is real, tested, and correct in every function probed here — and completely
unreachable by any agent connected to it today.

## Decisions for the user

- **[expose measure/detail as MCP tools]** — `measure` (distance/gap/angle/clipping/full
  report) and `detail` (bevel) publish zero tool specs, so the product's central marketing
  claim is currently unreachable by any connected agent. Options: (a) wire `MEASURE_SPECS`/
  `DETAIL_SPECS` now — low engineering cost, since `registry.py`'s `_load_optional` already
  round-robins in any module that publishes them, and every underlying function is already
  correct and tested; consequence is the `inspect`/`refine` role tool-count budget (~5-8
  per role, ADR-003) must absorb the new tools without pushing past the accuracy-optimal
  range. (b) Leave deferred and correct the README/marketing to stop claiming live
  verification until it is wired. Recommend (a): shipping with the flagship claim
  unreachable is worse than the budget cost. Impact: high. Evidence: live registry dump
  (`detail: []`, `inspect: []`), this review's code reading.

- **[wire AcceptanceQuery evaluation into perform()]** — `measure.evaluate(op.acceptance)`
  is never called anywhere outside tests. Options: evaluate on every mutating call (real
  cost — a geometry check per op) vs. gate it on the existing `CheckCadence` machinery
  (`EVERY_GEOMETRY_CHANGE` / `PHASE_BOUNDARIES` / `ON_REQUEST` — already built, already
  unused for this) vs. leave unwired. Recommend wiring at existing cadence granularity —
  the cost-control machinery already exists for exactly this purpose and sits idle.
  Impact: high. Evidence: `orchestration/reporting.py::perform` read in full; zero
  non-test callers of `measure.evaluate` (grep).

- **[auto-declare JoineryIntent for self-consistent ops, or expose it as a parameter]** —
  QA's B-00K is open because nothing produces a `JoineryIntent` for sockets an op
  deliberately creates; this review adds that nothing lets an *agent* declare one either,
  since no tool exposes the parameter. Options: auto-declare inside the op (fast, but the
  op self-certifies its own correctness — weakens the "never trust self-report" principle
  the product is built on) vs. add an optional `joinery` parameter to the relevant ops'
  input schemas, defaulting to none, evaluated once #1 and #2 are wired. Recommend the
  parameter route — it keeps verification external to the thing being verified. Impact:
  medium. Evidence: `docs/qa/report-1.md` B-00K; zero `joinery` references in `ops/`
  (grep, this review).

- **[track blender-ai-mcp and NVIDIA's Omniverse Agent Toolkit]** — the "no installable
  product does this" premise from the original survey is softening: a small open-source
  MCP addon now ships live geometry-assertion tools, and NVIDIA shipped a vendor-grade
  CAD-to-SimReady validation blueprint for Blender in July 2026. Neither is mature, but if
  either gains traction the differentiation this product is banking on narrows fast, and
  right now blender-ai-mcp already beats this product on live tool reachability alone.
  Options: monitor only, or benchmark this product's (currently unwired) measurement
  surface directly against blender-ai-mcp's exposed tool set once #1 ships. Recommend
  benchmarking before investing further in features that tool may already cover. Impact:
  medium. Evidence: `github.com/PatrykIti/blender-ai-mcp` (checked 2026-08-06);
  `nvidianews.nvidia.com`, 2026-07-20 (checked 2026-08-06).

- **[route construction ops through the constraint solver, or leave the two paths
  parallel]** — `ops/railing.py` and siblings hand-roll plumb/spacing logic rather than
  calling `constraints.solve`, even though `align` does so successfully for its own tools.
  Options: leave as-is (two independently-tested implementations of "plumb" — a drift risk
  over time) vs. refactor `ops` to call `constraints` (single source of truth, but touches
  `railing_test.py`, explicitly called out elsewhere as this codebase's flagship green
  suite). Recommend leaving as-is until a concrete bug demonstrates drift between the two —
  refactoring a green flagship suite for architectural symmetry alone is the kind of
  change the project's own module-ownership rules caution against. Impact: low. Evidence:
  grep confirming `ops/` never imports `constraints`; `ops/CLAUDE.md`'s own note calling
  this an implementation choice, not a requirement.
