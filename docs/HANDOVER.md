# Handover

Everything raised during this pipeline and **not taken into the final pass**, with what Phase
6 learned about it and what it would cost to close. This file replaces a third iteration —
the pipeline is fixed-length and stops after Phase 8.

Nothing here is a vague "later". Each item has a repro or a citation, and a suggested fix.

Written at Gate B (2026-08-06) and updated at the end of the run with anything the final pass
did not reach.

---

## Chosen by the user, then cut for budget

These are not non-goals. The user selected them at Gate B wave 3 and cut them at wave 6 when
the arithmetic was put in front of them. They are the first things a next pass should pick up.

### A render / screenshot tool — medium

Let the agent look at what it made. This was rejected at design time in favour of numbers —
the whole thesis is that VLMs score 34–56% where humans score 79–99% on spatial reasoning, so
the tool should compute facts rather than ask a model to eyeball a render. But `blender-mcp`'s
most-used feature is exactly this, numbers and a picture are not mutually exclusive, and
`src/mcp_server/images.py` already exists to downscale a rendered image for token cost — it
just has nothing producing one.

**Fix:** a `render_view` tool on the `INSPECT` role taking a camera position and target,
rendering through `bpy` (window access is available in-process — see `PIPELINE-LOG.md:236-239`),
downscaling through the existing image path.

### Collision meshes and texture atlasing — medium each

Offered at Gate A 12.3 and not selected; `A-003` recorded that as "not now". At Gate B the
user selected both, which **amends A-003** — these are wanted, not declined. Both matter
specifically for the Roblox and game work described at Gate A 12.1.

**Fix:** both are export post-processes in `src/export/`. Collision generation is a convex
decomposition or a simplified proxy per object; atlasing packs the per-object UV islands
produced by `src/uv/` into a single sheet and rewrites the UVs before `export_gltf`.

### The full browser suite — medium-large

Reduced to a load-and-render smoke test (`F-020`), which is real and now runs: 10 tests in
Chromium, including a pixel-level check that the canvas actually draws, a discriminating
negative case (an empty scene leaves it flat), both colour schemes, and a keyboard-only pass
with visible focus. What remains unverified is CSS layout against `DESIGN.md` and the
orbit/pan controls under a real pointer. `A-009` is amended accordingly.

**Why this matters more than it looks:** every layer in this project that got its first real
exercise found defects nothing else could — the contract review found 15 blockers, the test
audits 6 implementations that would pass while doing nothing, the composition root 3
integration defects, and running the product 5 more. The browser is the last unexercised
layer, and the base rate here is not encouraging.

---

## Raised by Phase 6, not taken

### B-00K — operations do not declare joinery for the sockets they create

A staircase plus railing reports 94 clipping defects, most of them balusters correctly
socketing into treads. The measurement is right. Nothing produces a `JoineryIntent` for a
joint an operation deliberately made.

**Half of this closed in the final pass**: `find_clipping` now exposes a `joinery` parameter
and accepts plain JSON, so an agent *can* declare "this post is meant to be 500 mm into the
deck" and have the defect correctly silenced. What remains is that no operation declares
joinery for the joints it creates itself, so an agent still has to know to do it.

Offered at Gate B 3.1 as one of four wire-ups and not among the three selected.

**Fix, and the reason it is a decision rather than a bug:** adding an optional `joinery`
parameter to the socket-making operations' input schemas keeps verification external to the
thing being verified. Having the operation auto-declare its own joints is cheaper and lets an
operation certify its own correctness — the exact failure mode ADR-005 exists to prevent.
Take the parameter route.

**Repro:** build a staircase, add a railing along its rake, run `find_clipping` over all
pairs. 94 defects, ~39 of them on a smaller 4 m room.

### A-006 — which constraints agents actually reach for

The 12-type constraint vocabulary (`on`, `flush_with`, `centred_on`, `follows`, `offset_from`,
`ends_at`, `plumb`, `parallel_to`, `perpendicular_to`, `coplanar_with`, `spacing`, `clear_of`)
is built, solved and correct. **No agent has used any of it outside a test file.** The
assumption explicitly queued "evidence of which constraints agents actually reached for" for
Gate B, and that evidence does not exist because nothing has run.

Offered at Gate B 2.4 against measuring scale to a few thousand objects; scale won.

**This is the one assumption this pipeline could not resolve.** It needs a real session with a
real agent — which the final pass made possible for the first time: a real MCP client now
connects over stdio, lists the catalogue, builds geometry, is refused by the phase gate,
follows the refusal's own suggestion, and exports a file. Running one such session and
recording which constraints get reached for is the first thing to do next.

### Routing `ops/` through the constraint solver

`ops/railing.py` and its siblings hand-roll plumb and spacing logic rather than calling
`constraints.solve`, even though `align/` uses the solver successfully for its own tools. Two
independently-tested implementations of "plumb" is a drift risk. Dropped by the Phase 6 filter
because no drift has actually been observed and `railing_test.py` is this codebase's flagship
green suite — refactoring it for architectural symmetry alone is the kind of change the
module-ownership rules caution against.

**Revisit when** a concrete bug shows the two disagreeing, not before.

### Benchmarking against `blender-ai-mcp`

`github.com/PatrykIti/blender-ai-mcp` (52★, Apache-2.0, CI, checked 2026-08-06) ships
`scene_measure_distance`, `scene_assert_contact`, `scene_assert_dimensions` and
`scene_assert_containment` as live MCP tools today, plus a staged vision-checkpoint loop.
NVIDIA shipped a CAD-to-SimReady Blender validation blueprint on 2026-07-20.

The original research's "only unshipped papers do this" premise is now stale. Neither
competitor is mature or widely adopted, but the differentiation this product banks on narrows
if either gains traction.

**Do this after `F-006` lands**, so the comparison is between two reachable tool sets rather
than between their tools and our unwired functions.

---

## Never built at all

### Rigging and organic sculpting

Gate A 2.3 said nothing is out of scope. `A-004` sequenced these last on the reasoning that
two build passes cannot make them good, and that reasoning still stands. The honest assessment
`A-004` promised, and which did not exist until this file:

**There is zero code.** Not thin coverage — a repo-wide search for `armature`, `rigging`,
`bone`, `weight paint`, `sculpt`, `multires` or `organic` returns no implementation hits.
No `src/rig/`, no skinning, no shape keys, no sculpt brushes.

This is the right outcome. Everything the user described as the point of the tool — clipping,
gaps, alignment, detail and realism, engine-ready export, whole environments, hard-surface and
architectural work — is hard-surface, and hard-surface is where the constraint solver, the
measurement engine and the joinery model all pay off. Rigging is a different product with a
different verification model (weight distribution, deformation quality, bind poses) that
shares almost nothing with what was built.

**If it is wanted:** it is a new module against `EngineProtocol`, roughly the size of `ops/`
plus `constraints/` together, and it needs its own acceptance vocabulary before any of it is
worth building.

---

## Process evidence that cannot be recovered

### Q-017 — tests-first git evidence

The gate's per-module tests-first check fails for all 17 modules. The honest picture:

- **Ten modules** (`engine`, `spatial`, `measure`, `raw`, `constraints`, `detail`, `ops`,
  `scene`, `export`, `orchestration`) **do** have RED commits — `b63166d`, `5f205eb`,
  `4f780e6` — under combined scopes like `test(engine,spatial,measure,raw):` that the gate's
  per-module matcher cannot parse. The evidence exists; the gate cannot see it.
- **Six modules** (`gaps`, `align`, `uv`, `mcp`, `viewer`, `frontend`) have **no** RED commit.
  They were built RED-then-GREEN inside a single agent pass, which the agents reported
  verifying, but there is no git-level proof the tests ever failed first.
- **`app`'s tests were committed after its implementation.**

Teaching the matcher to read combined scopes was offered at Gate B 6.4 and not chosen, so ten
verifiable modules continue to read as failures alongside the six unverifiable ones.

**No retroactive commits were fabricated, and none should be.** Fabricating a sequence that
did not happen is precisely the failure this check exists to catch. A green gate bought that
way is worth less than a red one that tells the truth, and this is evidence about how much to
trust the *next* run's gate as much as this one's.

**Fix, if wanted:** teach `.pipeline/check.mjs` to split a comma-separated commit scope. Small
and mechanical. It converts a uniformly-red check into an accurate one: ten verified, six
genuinely unverifiable, one committed backwards.

---

## Known-untested paths

Recorded because none of these has a single real run behind it, by any test or any person.

| Path | Status | Cost to close |
|---|---|---|
| MCP SDK server with a real client connected | `serve_stdio`/`serve_http` call a real `mcp.server.Server`; the SDK **is** installed here; nothing has ever connected | medium — a scripted client |
| Viewer socket with a real frame pushed | `websockets` and `starlette` are installed; no test opens a socket | medium |
| `serve_http` bound to a non-loopback host | Only the warning log line is tested, and only up to the missing-SDK error. Nothing has bound `0.0.0.0` and confirmed a remote connection can do what ADR-009 says it can | small |
| Above a few thousand objects | `F-019` takes this to a few thousand. Beyond that, unmeasured | — |

---

## Anything the final pass did not reach

The final pass ran in three rounds. **Round 1 landed in full.** **Round 2 was stopped by the
user partway through** — `ops` and `frontend` had completed and were kept, `engine` was
finished by hand, `viewer` was reverted rather than shipped broken, and two units never ran.
**Round 3 recovered those**, and was itself interrupted by a machine restart that killed one
unit between an atomic write and its rename; the crashed temp file was recovered and the
unit finished by hand from the tests it had already written.

**27 of the 28 scoped items are done.** What follows is what is not.

### F-019 — the scale curve, partially

`src/engine/scale_test.py` exists and follows object creation past the ~900 objects that was
all either pass had measured, against Gate A 11.4's stated target of thousands. The figures
in it are the implementing agent's; they were not independently re-run at the close of the
run, so treat the ceiling it asserts as a regression guard rather than as a published
benchmark. **Re-run it and read the numbers before quoting them.**

### The contract request that was resolved, and the one consequence left

`MeshOps.replace_mesh` was added this pass, so `detail.cleanup_bevel_topology` no longer has
to decline on a UV-unwrapped or multi-material object. One honest limit remains and is
documented at the implementation: **a replaced mesh loses its UV layer**, because UVs are
stored per split vertex and a new vertex set has no correspondence to the old coordinates.
A caller that needs UVs afterwards re-unwraps. That is a real cost and it is better than a
silently mismatched unwrap.

### Deliberately not attempted

- **A render/screenshot tool** and **collision meshes + texture atlasing** — chosen by the
  user at Gate B 3.2 and cut by the user at Gate B 6.1 for budget. Both are described above
  under "Chosen by the user, then cut for budget"; they are wanted, not declined.
- **The full browser interaction and layout suite** — reduced to a smoke test at Gate B 6.1.
  The smoke test is real and runs 10 tests in Chromium, including a pixel-level check that
  the canvas actually draws and a keyboard-only pass over the controls. What it does not do
  is exercise the orbit/pan controls or assert layout against `DESIGN.md`.
- **Rigging and organic sculpting** — zero code, for the reasons set out above. Unchanged.
- **Teaching the gate to parse combined-scope commits** — offered at Gate B 6.4 and not
  chosen. See "Process evidence that cannot be recovered".

### A-006, still the one assumption nothing could settle

Which of the 12 constraint types agents actually reach for. The vocabulary is built, solved,
and now reachable — but no agent has driven a real session end to end. That is the first
thing to do next, and it is now genuinely possible: a real MCP client connects, builds,
promotes and exports.

