# forge3d

Live 3D authoring for AI agents. It computes the spatial facts so the model never has to
guess them.

## Why it works this way

Across seven independent spatial-reasoning benchmarks, frontier vision models score
**34–56% where humans score 79–99%** — and the gap is worst on exactly the judgements a 3D
authoring loop needs: left/right, near/far, distance, occlusion, viewpoint change.

Every existing agent-to-3D bridge hands the model a screenshot and asks it to place things
by eye. That is the architecture, and it is also why the output looks like boxes glued
together.

So this tool takes those judgements away from the model:

- **It measures.** Ten defect classes and seven metric queries, computed and handed over as
  numbers — manifoldness, clipping depth, gap width, angles, scale, polygon budget.
- **It takes relationships, not coordinates.** `follows`, `flush_with`, `plumb`, `spacing`,
  `clear_of` — resolved by a solver. Published work puts constraint-plus-solver placement at
  **91–95%** against **37%** for a model producing raw coordinates.
- **It verifies by re-measuring.** A task is done when the query that defined it comes back
  clean — never because an agent said so. Agents self-report false success **13–89%** of the
  time, and a second agent reviewing that claim catches it at barely above chance.

The model keeps intent, taste, and sequencing. The tool keeps the geometry.

## Quick start

```bash
python src/forge3d_cli.py doctor        # what is installed, and is it wired?
python src/forge3d_cli.py serve         # stdio — Claude Desktop / Claude Code / Cursor
python src/forge3d_cli.py serve --http  # streamable HTTP — ChatGPT developer-mode connector
```

Both transports exist so a **subscription you already pay for** can drive the tool, with no
API key and no per-token billing on top.

Requires Blender 5.2 and Python 3.13 (`bpy` is version-locked to 3.13 exactly). Without
Blender it still runs on an in-memory engine and says so loudly at startup — enough to
exercise the system, never enough to produce an asset.

## What it can do

| | |
|---|---|
| **Build** | primitives, walls, floors, openings, staircases, railings, arrays along curves, LOD chains, grid-aligned modular kits |
| **Fix** | boundary holes, non-manifold edges and vertices, loose and duplicate vertices, flipped normals, disconnected shells, visual gaps between parts |
| **Align** | parallel, perpendicular, coplanar, plumb, flush, grid snap, exact angles — quaternion-composed, so hundreds of small agent edits do not accumulate gimbal error |
| **Detail** | heuristic bevels on edges that would plausibly catch light, panel lines, greebles with deliberate rest zones, roughness variation, physically-plausible albedo |
| **Finish** | UV unwrap with agent-overridable seams, PBR bake, polygon budgets |
| **Export** | Roblox (studs), Unity, Unreal, Godot — each with its own audited axis, handedness and unit conversion |

## The things that are easy to get wrong, and are not

- **Railing posts stand plumb on a slope.** Posts normal to a stair rake is *the* classic
  naive-generator error. Spacing is measured along the path's arc length, a post is forced at
  every direction change, and the top rail terminates at post centrelines.
- **A socket is not a clipping bug.** A post embedded 30 mm into a deck and two posts
  overlapping by 30 mm are identical geometry. The difference is declared intent, and no
  library can infer it — so `JoineryIntent` makes it explicit.
- **Unity gets both the X mirror and the rotation-sign flip.** One without the other is a
  silent mirroring bug you discover hours later in a different tool.
- **Undo is a pointer move, not a snapshot.** Per action, plus named checkpoints. Raw code
  execution creates an explicit barrier with a real snapshot, because it cannot be replayed.

## Multi-agent

Many sub-agents read, measure and propose in parallel; **exactly one writes**. A live 3D
scene is shared mutable state, which is the case where parallel LLM writers are measured to
make conflicting implicit decisions and corrupt each other's work.

Work splits by phase — blockout → refine → detail → polish — which gives mutual exclusion
for free. Colliding proposals are surfaced with the exact geometry involved, like a merge
conflict; they are never silently resolved, because for geometry a silent overwrite produces
an invalid model rather than a surprise.

Each role sees **5–8 tools**, never the whole catalogue. The accuracy-optimal visible set
measures around 2–7; past ~30, agents start inventing tool names and borrowing argument
schemas from the wrong tool.

## Live view

A browser view at `frontend/index.html` shows the model as it is built, with an action log
and the latest change highlighted — plus pause, roll back N steps, and redirect in words,
mid-run.

## Security

**There is no sandbox.** A connected agent can run arbitrary code and touch any file you
can. That was chosen deliberately for a private, local, single-user tool — read
[docs/SECURITY.md](docs/SECURITY.md) before exposing it to anything else, and do not bind
the HTTP transport off loopback.

## Documentation

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | the module map, the seams, and four things it got wrong |
| [docs/TESTING.md](docs/TESTING.md) | both suites, and why the fake engine is a real engine |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | the RED → AUDIT → GREEN → REVIEW loop |
| [docs/SECURITY.md](docs/SECURITY.md) | what a connected agent can do |
| [docs/decisions/gate-A.md](docs/decisions/gate-A.md) | the 48 decisions this was built from |
| [docs/adr/](docs/adr/) | 11 architecture decisions and why |
