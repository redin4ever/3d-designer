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
