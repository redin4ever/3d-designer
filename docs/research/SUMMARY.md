# Research summary — Phase 1

Synthesis of `landscape.md`, `flows.md`, `domain.md`, `technical.md`, `agent-ergonomics.md`.
All research dated 2026-08-05. This is the file later phases read; the five raw files exist to
be cited, not re-read.

## The product in one paragraph

A tool that lets AI agents author and refine 3D models live — filling gaps, raising detail and
realism past "stitched-together boxes", fixing angles and part clipping, and coordinating
sub-agents on one scene. What the research clarified is **what kind of tool that has to be**.
Across seven independent spatial benchmarks, frontier VLMs score **34–56% where humans score
79–99%**, and the gap is worst on exactly the judgements this work needs: left/right, near/far,
distance, occlusion, viewpoint change. So the tool cannot be a thin bridge that hands a model a
screenshot and asks it to eyeball placement — that is the architecture of every existing tool
and it is also the reason their output looks like glued boxes. The tool's job is to **compute
every spatial fact and hand the model verified numbers**, accept **declarative constraints**
rather than raw coordinates where possible, and **verify every result programmatically** rather
than trusting either the model's self-report or a second model's opinion. The model keeps
intent, aesthetics, decomposition and sequencing. That division of labour is the product.

## Comparable products

| Name | Bucket | What to steal | What to avoid |
|---|---|---|---|
| **blender-mcp** (ahujasid) | agent↔Blender bridge, de-facto standard | Thin socket protocol; viewport-screenshot tool; asset-library integration (Poly Haven) | Unsandboxed `exec()` — **open CVSS 9.0 RCE, issue #304**; 5-min timeouts (#279); no checkpoint (README says "ALWAYS save your work first") |
| **BlenderGPT / Blender Copilot** | add-on, prompt→script | "Describe → run → history log" UX | No visual feedback loop at all; no geometry validation |
| **Infinigen** (Princeton, BSD-3) | procedural | Existence proof that pure procedural rules reach photorealism, no AI, no asset library | Not agent-driven; authoring a generator needs an expert, not a prompt |
| **Meshy / Tripo / Rodin / CSM / Kaedim** | text/image→3D, $0.20–0.40/gen | Fast concept bootstrap; Rodin's explicit quad-vs-tri + polycount tiers | Vendors *self-admit* unresolved topology/UV/scale; Tripo ships "dimensionless" meshes and calls scale "the root cause of most integration problems" |
| **Zoo/KittyCAD Text-to-CAD** | LLM→parametric CAD | Exact, manufacturable, solid-body output — closest to "LLM writes real CAD" | Narrow (mechanical parts); metered $0.0083/s penalises long agent loops |
| **CadQuery / build123d** (Apache-2.0) | programmatic B-rep | Watertight-by-construction; build123d's context-manager API is more LLM-friendly | LLM-written code is "sometimes spatially incoherent"; no visual feedback |
| **trimesh / Open3D** (MIT) | repair/validate | `is_watertight`, manifold checks, normal fixing as an automatable QA gate | Repairs symptoms not causes; **no semantic understanding** — cannot tell a correct socket from a clipping bug |
| **Geometry Nodes kitbash/scatter** | procedural detail | Scatter/greeble graphs are the template for "add detail after blockout" | Node graphs are brittle for an LLM to author; API shifts between versions |

Research prior art for the loop itself: **BlenderAlchemy** (ECCV'24, edit-generator + GPT-4V
evaluator), **SceneCraft** (ICML'24, +45.1%/+40.9% CLIP over one-shot BlenderGPT), **LL3M**
(2025, agent team + self-critique), **I-Design** (5 role-agents on one interior), **LLMR**
(CHI'24, **4× lower error** than raw GPT-4), **Holodeck** (CVPR'24, constraint solver, 64.4%
human preference). All papers. **None shipped as an installable tool.**

## The two or three journeys that make or break this

1. **The agent loop: perceive → plan → act → verify.** The whole product. Perception is a
   scene-graph *diff* every call (cheap, exact) + deterministic geometry queries as the hard
   gate + multi-view renders only at checkpoints (a 1024² image ≈ 1,334 tokens). Verification
   is programmatic first, rendered judgement second, model opinion never as the sole gate.
2. **Blockout → refine → detail → polish.** This staged progression is *why* human work does not
   look like glued boxes — blockout is deliberately boxes, and later passes exist specifically
   to convert them. Today's AI 3D tools skip the middle. An agent can own blockout, retopo/UV
   (as algorithm orchestration), and partial texture/lighting; it cannot yet own organic
   sculpting or rigging.
3. **Steer and recover mid-build.** No surveyed tool has checkpoints. Long runs with no progress
   signal leave operators unable to distinguish "working" from "stuck", and a bad result after a
   long wait is worse than a fast miss.

## Table stakes — absence is a defect, not a choice

- Mesh validity checks (manifold, watertight, self-intersection, loose/duplicate verts, normals)
  as an automatic gate — `is_edge_manifold`, `is_vertex_manifold`, `is_self_intersecting`.
- Unit anchoring. 1 unit = 1 metre, pinned. Tripo's own blog names dimensionless output as the
  root cause of most integration problems.
- Applied scale before any bevel/boolean/physics — unapplied non-uniform scale silently corrupts
  all three and is invisible in the viewport.
- glTF/GLB export with metal-rough PBR; `.blend`-equivalent working format that keeps parametric
  history so later edits are possible.
- Undo/checkpoint. Every surveyed tool lacks it; the reference implementation tells users to save
  manually first.
- Progress signal during long runs.
- Axis/handedness conversion centralised in one audited place (Blender Z-up RH → glTF Y-up RH →
  Unity Y-up **LH** is a documented, repeated bug chain).

## Differentiators available, each with a cost

| Differentiator | Why it is available | Cost |
|---|---|---|
| **Ship the render→critique→edit loop** | Exists only in three unshipped papers | The loop is the whole engineering effort |
| **Tool-computed spatial truth** (no eyeballing) | Nobody does this; every bridge hands the model a screenshot | Needs a real geometry query layer, not a bpy passthrough |
| **Constraint-DSL placement + solver** | LayoutGPT/NSR-1K measured **91–95%** vs SpatialVLM's **37%** within 2× on raw coordinates | Must author a constraint vocabulary and a solver |
| **Semantic intersection model** (socket vs clip) | No library on earth distinguishes intended from unintended overlap — BVH sees both identically | Parts must carry declared joinery intent |
| **Programmatic definition-of-done** | Agents self-report false success **13–89%**; LLM judges catch it at **AUROC ≤0.65** | Every task needs a machine-checkable acceptance spec |
| **Heuristic bevel pass** | Most-cited realism lever across sources | Consensus, *not* a measured study — and uniform beveling is itself a tell |
| **Safe execution** | The standard bridge has an open CVSS 9.0 RCE | A validated tool surface is more work than `exec()` |

## Hard constraints — no gate answer changes these

1. **This machine has no Blender and no Python.** Only the Windows Store `python3.exe` stub.
   `bpy` 5.2.0 requires **exactly Python 3.13** and is a 338 MB wheel. Node v24.18.0 and git are
   present. **A test suite that requires Blender or Python cannot run here.**
2. **`bpy` is GPL-3.0.** Settled: distributing an add-on or a binary that embeds it triggers
   copyleft. Contested: `import bpy` into a distributed process. Broadly agreed: GPLv3 has no
   network clause, so a hosted service does not trigger it. Subprocess isolation is the
   defensible middle. PyMeshLab and openscad-wasm carry the same problem; trimesh/Open3D (MIT),
   manifold-3d (Apache-2.0), three.js (MIT), OCCT (LGPL) do not.
3. **Blender's Python API breaks between versions** with no deprecation policy — 4.0 renamed
   Principled BSDF sockets, 5.0 renamed Grease Pencil to Annotation, 3.2 replaced context-override
   dicts. Every version bump is a real engineering cost. Blender is at **5.2 LTS (2026-07-14)**.
4. **Many `bpy.ops` operators fail headless** on `poll()` needing a window/screen/area. The data
   API (`bpy.data`, `bmesh`) is the reliable path; `temp_override()` only when unavoidable.
5. **Tool-count degrades accuracy.** Chance-corrected optimum is **K ≈ 2.3–7.4** visible tools;
   RAG-MCP measured 13.62% → 43.13% selection accuracy with retrieval. Past ~30 tools,
   description overlap causes real confusion. This forces role-partitioned toolsets.
6. **MCP `ImageContent` is a token footgun** — several clients pass base64 through as text at
   **15–25k tokens per image** instead of ~1,600. Verify the client or bypass the tool-result path.
7. **Non-convex mesh-mesh penetration depth is unsolved.** FCL returns 0 depth on genuine
   contact; robust depth needs at least one convex shape.
8. **No production-ready incremental glTF/USD streaming format exists.** Live view is either full
   GLB reload per checkpoint (~1–3 s) or a custom WebSocket diff protocol.

## Where the evidence contradicts the intuition

- **Multi-agent is not free.** Anthropic measured **+90.2%** on research quality but at **~15×
  the tokens**. Cognition argues against it and names the failure mode: conflicting implicit
  decisions on *shared mutable state*. A live 3D scene is exactly shared mutable state — the
  Cognition shape, not the Anthropic shape. The reconciliation both sides converged on is
  **many parallel readers, one writer** (or fully isolated copies merged afterwards). The user
  asked for multi-agent, so the question is not whether but *in which shape*.
- **Self-critique is not a gate.** Models "defensively justify" their own output (VISCO's
  self-correction blind spot). Cross-model VLM judging reaches κ=0.66 but only when the defect
  is visually obvious, and falls to chance on ambiguous calls.
- **Over-composite tool calls hurt too.** SheetCopilot measured **−12.6% Exec@1** collapsing a
  task into one high-level call. The answer is a middle skill library of typed parametric
  operations, not "one tool per primitive" and not "one tool per finished object".
- **"Bevel everything" is practitioner consensus, not a measured result** — and the same sources
  warn that uniform beveling is itself an artificiality tell. Only plausibly-worn exposed edges.

## The railing, worked — the user's own example

A correct railing is: posts instanced at regular spacing along a curve, each **vertical in world
+Z regardless of path slope** (posts normal to the stair rake is *the* classic naive error);
posts additionally inserted **exactly at direction changes**, not just on the fixed pitch; top
rail swept at constant offset above the tread nosing and terminating **at post centrelines**;
balusters plumb through slope changes, spaced so a 4-inch sphere cannot pass (IRC §R312.1.3);
handrail 34–38 in above nosing; guard ≥36 in residential / ≥42 in commercial. The correct
primitive is **array-along-curve / instance-on-points over a resampled curve**, never per-instance
placement. Every failure mode the user described is a symptom of doing it the naive way.

## Open questions → Gate A

50 raw decisions across the five research files, deduped into **34 questions** in
`.pipeline/question-backlog.json`, grouped into eight waves: `scope`, `architecture`,
`agent-interface`, `geometry`, `realism`, `multi-agent`, `ux`, `quality-bar`. Each carries a
recommended default and its evidence. Gate A asks all of them.
