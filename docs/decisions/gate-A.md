# Gate A — 2026-08-05

12 waves, 48 decisions. The user's verbatim notes are reproduced exactly where given; they
outrank the option label they sit beside.

---

## Wave 1 — Who and why

| # | Question | Chosen |
|---|---|---|
| 1.1 | Who is on the other end most of the time? | **An AI agent driving it, human watching** |
| 1.2 | What does "it worked" look like? | **Drops into a game engine or printer** — production-ready |
| 1.3 | What would make you abandon it? | **Still looks like glued boxes** |
| 1.4 | What must v1 be good at building? | *(verbatim)* "it can be used for whole enviorments and hard-surfaces and architectual" |

**1.2 is the highest bar of the three offered** and pulls UVs, materials, manifoldness and
correct scale into v1 scope. **1.3 makes realism the deal-breaker**, so detail passes are not a
nice-to-have. **1.4 takes all three** of hard-surface, architectural *and* whole environments —
the answer was not one of the offered options and is recorded as given.

## Wave 2 — Scope

| # | Question | Chosen |
|---|---|---|
| 2.1 | Which capabilities in v1? | **All four**: clipping/interpenetration, gap & hole repair, angle/alignment/snapping, detail & realism passes |
| 2.2 | How far does "engine-ready" go? | **Full — UVs and baked texture maps too** |
| 2.3 | What is out of v1? | **Nothing — attempt everything** |
| 2.4 | Call paid 3D-gen services? | **No — the tool and agent author everything** |

**2.3 was flagged at the time**: attempting everything (including rigging and organic sculpting,
which research says agents cannot reliably own) across two build passes means some areas land
thin. Accepted by the user; thin areas go to `docs/HANDOVER.md` with an honest assessment rather
than being silently dropped.

## Wave 3 — The agent loop

| # | Question | Chosen |
|---|---|---|
| 3.1 | How often to check the agent's work? | *(verbatim)* "after every change that touches geometry with a settings menu setting that enables me changing that" |
| 3.2 | What does an agent get on an empty scene? | **A staged plan: blockout → refine → detail → polish** |
| 3.3 | How big is one agent action? | **Typed parametric operations** |
| 3.4 | How does an agent say where something goes? | **Relationships, with coordinates as escape hatch** |

**3.1 adds a requirement no option carried**: check cadence is user-configurable at runtime, not
a constant. **3.3 + 3.4 together define the tool surface**: a curated library of typed, named,
parameter-validated modelling operations, taking declarative constraints by default.

## Wave 4 — Feedback and recovery

| # | Question | Chosen |
|---|---|---|
| 4.1 | What comes back after an action? | **What changed + key measurements + new problems** |
| 4.2 | What does a failed operation say? | **Which rule broke** — *(verbatim)* "what rule it broke also note i will use this to make for example game designs" |
| 4.3 | How much can be undone? | **Every action, plus named checkpoints** |
| 4.4 | How much without being asked? | **Fully autonomous — never stop** |

**4.2 is the most consequential note in the gate.** The use case is game design. That makes
engine-ready export, polygon budgets, axis/handedness conversion and modular level pieces
first-class rather than incidental, and it is why waves 11–12 exist.

**4.4 with 1.1** means: runs to completion without gating, but a human is watching and can
intervene (see 5.4).

## Wave 5 — The interface

| # | Question | Chosen |
|---|---|---|
| 5.1 | Is there a browser UI? | **Yes — live 3D view plus an action log** |
| 5.2 | What should it look like? | **`linear.app`** — near-black engineering console |
| 5.3 | What do you see during a build? | **Live 3D + action log + latest change highlighted** |
| 5.4 | Can you take the wheel mid-run? | **Pause, roll back N steps, redirect in words** |

The user was told they could name any of the other 71 catalogue systems, supply a file or URL, or
describe a brand to author from. They chose from the shortlist. `.pipeline/design-candidates/linear.app.md`
becomes root `DESIGN.md`.

## Wave 6 — Content and data

| # | Question | Chosen |
|---|---|---|
| 6.1 | What is a model stored as? | **Both — parametric working file, glTF on export** |
| 6.2 | Is 1 unit = 1 metre? | **Locked by default, changeable per scene** |
| 6.3 | Export with problems? | **Allowed, with a warning banner** |
| 6.4 | Built-in real-world dimensions? | **No — the agent supplies every dimension** |

**6.4 removes a module.** No IRC/IBC code table, no built-in stair-rise or handrail defaults. The
tool checks *consistency and validity*, not conformance to real-world norms. This is coherent
with game work, where scale is often deliberately unreal.

**6.3 requires the geometry checks to exist and run** even though they do not block — the warning
banner needs their output, as does 4.1's "new problems" field.

## Wave 7 — Where it runs, and what it may do

| # | Question | Chosen |
|---|---|---|
| 7.1 | Where does it run? | **On your own machine** |
| 7.2 | Arbitrary code execution? | **Yes, unrestricted** |
| 7.3 | What happens to the codebase? | **Private — yours only** |
| 7.4 | What files may an agent touch? | *(verbatim)* "anywhere on disk also make sure it supports my subscriptions eg: chatgpt subscription so that i can use it with it" |

**7.2 was chosen with the risk stated in the option text** (the standard agent–Blender bridge
carries an open CVSS 9.0 RCE through exactly this design). It is a private, local, single-user
tool, so the exposure is the user's own machine and their own agents. Built as asked;
`docs/SECURITY.md` documents the exposure plainly and the capability is not hidden.

**7.3 resolves the GPL question completely.** Private and never distributed means Blender's GPL
imposes no obligation. `bpy`, PyMeshLab and any other GPL component may be used freely. This is
what makes 9.2 viable.

**7.4's second clause is a product requirement, not a file-access answer** — it is what made
wave 11's MCP question necessary.

## Wave 8 — Quality bar

| # | Question | Chosen |
|---|---|---|
| 8.1 | Who decides work is correct? | **The agent looks at a render and judges** |
| 8.2 | How is a sub-task marked done? | **A reviewing agent confirms it** |
| 8.3 | How aggressively to bevel? | **Only edges that would plausibly catch light** |
| 8.4 | Which detail passes exist? | **Edge treatment; surface detail (panel lines, seams, greebles); material realism (varied roughness, no pure black/white, wear)** |

**8.1 and 8.2 were both flagged at the time** as the two options research measures as unreliable —
models defensively justify their own output, and reviewing agents are fooled by confident
phrasing at barely-above-chance rates. The user's choice stands. It was reconciled in wave 11.3
rather than overridden: measurements decide hard facts, the agent decides appearance.

**8.4 did not select the proportion & scale pass**, consistent with 6.4.

## Wave 9 — Stack

| # | Question | Chosen |
|---|---|---|
| 9.1 | How does your subscription reach it? | **MCP server** |
| 9.2 | Does it need Blender? | **Yes — Blender is the engine** |
| 9.3 | How exact must geometry be? | **Mesh-based, with strict validity checks** |
| 9.4 | Where must tests run? | **Require the full toolchain first** |

**9.2 + 9.4 together were a blocker** — neither Blender nor Python existed on the machine, so
nothing could have been tested. Resolved in wave 11.1.

## Wave 10 — Ways of working

| # | Question | Chosen |
|---|---|---|
| 10.1 | Concurrent writers? | **Many look and propose, one applies** |
| 10.2 | How is work split? | **By phase — blockout, refine, detail, polish** |
| 10.3 | On collision? | **Flag it with the exact geometry, like a merge conflict** |
| 10.4 | How to spend pass one? | **Everything as fully as possible** |

**10.2 matches 3.2** — the staged plan and the sub-agent split are the same structure, which
means phase gating does double duty as concurrency control.

## Wave 11 — Follow-ups (what earlier answers opened)

| # | Question | Chosen |
|---|---|---|
| 11.1 | Toolchain, given 9.2 + 9.4 | **Install both now — approved** |
| 11.2 | Which MCP client day one? | **Both — stdio and HTTP** |
| 11.3 | Measurements vs visual judgement? | **Measurements win on hard facts, agent wins on looks** |
| 11.4 | How big does a scene get? | **Thousands — a full game level or district** |

**11.1 executed and verified**: Blender **5.2.0 LTS** at
`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`, Python **3.13.14** at
`%LOCALAPPDATA%\Programs\Python\Python313\python.exe`. Both confirmed running.

**11.3 is the reconciliation of 8.1/8.2 with 1.2.** Non-manifold, clipping, wrong scale and
unapplied transforms are decided by measurement because an engine will agree with the
measurement. "Does this look convincing" stays the agent's call.

**11.4 is a significant architecture commitment** — thousands of objects needs spatial indexing,
partial loading and a live view that does not re-send the world on every change.

## Wave 12 — Game pipeline

| # | Question | Chosen |
|---|---|---|
| 12.1 | Target engine? | *(verbatim)* "it should manage for all as i might use roblox's engine usually" |
| 12.2 | Polygon budget? | **Track and warn against a budget you set** |
| 12.3 | What else does a game asset need? | **Modular / snapping pieces; LODs** |
| 12.4 | How automatic is texturing? | **Auto-unwrap and bake, agent can override seams** |

**12.1 means all four targets**, with **Roblox as the primary** since that is the user's usual
engine. Roblox is not one of the offered options and has its own constraints (studs, per-MeshPart
triangle limits) — it gets its own export profile, not an afterthought.

**12.3 did not select collision meshes or texture atlasing.** Both go to the backlog at low
priority rather than into v1.

---

## What this adds up to

An **MCP server (stdio + HTTP)** exposing a curated library of **typed parametric modelling
operations** that take **declarative constraints**, backed by **Blender 5.2 as the geometry
engine**, storing a **parametric scene document** that generates glTF on export. It runs
**locally and fully autonomously**, checks geometry after every change at a **configurable
cadence**, supports **per-action undo and named checkpoints**, and can be **paused, rewound and
redirected** mid-run from a **live browser view in the `linear.app` register**. Sub-agents split
**by phase**, many reading and proposing while **one writes**. Output targets **Roblox first**,
then Unity, Unreal and Godot, with **polygon budgets tracked**, **LODs and modular snapping
pieces generated**, and **auto UV unwrap and bake** with agent-overridable seams. Correctness is
decided by **measurement for hard facts and by the agent for appearance**.
