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

Reduced to a load-and-render smoke test (`F-020`). Real keyboard interaction, CSS layout
against `DESIGN.md`, focus order, and the orbit/pan controls in an actual browser remain
unverified. `A-009` is amended accordingly.

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
joint an operation deliberately made, **and no tool schema exposes a `joinery` parameter**, so
an agent cannot declare one either.

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
real agent, which is the first thing to do after the run ends.

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

The final pass ran in two rounds. **Round 1 landed in full** (F-001 to F-018, all committed
and green). **Round 2 was stopped by the user partway through**, so four of its six units
never ran and two were half-applied and reconciled per Rule 6.

### Reconciled at the stop

| Unit | State | What was done |
|---|---|---|
| `ops` | **complete, kept** | F-021 and F-013's ops half landed before the stop and are green |
| `frontend` | **complete, kept** | Puppeteer installed, `frontend/tests-browser/` written |
| `engine` | **half-applied, finished by hand** | F-023 done (`prefer_subprocess` deleted, `ARCHITECTURE.md` and `engine/README.md` corrected). F-019 and F-025 were not started |
| `viewer` | **half-applied, reverted** | The agent had written a real socket test suite (RED) and partially changed `bridge.py`/`translate.py`, leaving 11 failures. Reverted to the last green commit rather than shipping a broken module. `git show 30954de` is the baseline it returned to |
| `mcp-live` | **never ran** | — |
| `geometry-consistency` | **never ran** | — |

### Not done, in priority order

1. **F-002/live — the MCP SDK is 2.0 and the transport is written against 1.x.**
   Found and honestly filed by the round-1 `mcp_server` agent rather than hidden.
   `transports._build_server` uses `Server.list_tools()` / `Server.call_tool()` decorators,
   which 2.0.0 dropped for `mcp.server.MCPServer.add_tool`. It refuses by name rather than
   raising from inside the SDK, so **no live client can connect over stdio or HTTP today.**
   Everything behind the transport works — `dispatch` is verified end to end against real
   Blender — so this is wiring, not design. `src/mcp_server/CLAUDE.md` has the detail under
   "Known gap". **This is the highest-value single item left**: Gate A 7.4 (drive it from a
   consumer subscription) and Gate B 6.2 (the multi-agent guarantee) both run through it.

2. **F-009 — `forge3d serve` still does not start the viewer socket.** Gate B 1.3 chose
   auto-start. `viewer.serve()` is real and exported and nothing calls it, so no browser can
   reach a running session. The CLI change is small; the viewer work under it is not (see 3).

3. **The viewer socket has never carried a frame, and emits 5 of 13 message types.**
   `frontend/src/main.js` fully handles `HIGHLIGHT`, `LOG`, `PROBLEMS`, `CONFLICT`,
   `EXPORT_REPORT` and `RUN_STATE`; the backend constructs none of them, because
   `translate.py` only ever sees a raw `SceneChangeEvent` and never `perform`'s
   `ActionReport`. So Gate A 5.3's "latest change highlighted" shows nothing during a real
   run. The reverted round-2 work had started exactly here — a `serve(bridge=...)` seam plus
   a `report.py` translation path — and that is the shape of the fix.

4. **F-019 — the scale curve past ~900 objects.** Gate B 2.4 chose to measure to a real few
   thousand. Object creation is 0.78 ms/op at 900 and near-flat there; the stated target is
   thousands and the curve was never followed further, in either pass.

5. **F-025 — `_triangle_normal` exists four times and the copies disagree.**
   `align/position.py:41`, `constraints/anchors.py:78`, `detail/edges.py:162`,
   `uv/seams.py:71`. All four use `EPSILON` correctly since QA round 2, but three return
   `None` on a degenerate triangle and `constraints/anchors.py:82` returns `Vec3(0,0,0)` and
   then layers a second, undocumented `1e-9` threshold at `:95`. Nothing breaks today
   because each caller matches its own copy — the danger is that "make anchors consistent
   with the others" is exactly the drive-by edit that reintroduces the bug at `:95`.
   **There is a live half to this**, found by the round-1 `detail` agent: `detail/edges.py`
   treats anything under `EPSILON` (1e-4) as degenerate, which on real post-bevel geometry
   silently drops legitimate sub-millimetre corner triangles from the sharp-edge proxy. A
   4 mm bevel strip on a 1 m edge produces triangles well under that. `detail/topology.py`
   already normalises by hand against `1e-15` for this reason.

6. **F-013's remaining half — bare `ValueError`s in the geometry helpers.** `ops` got its
   share. `align/_geom.py`, `constraints/_orientation.py`, `constraints/_position.py` and
   `uv/unwrap.py` still raise unnamed errors that reach an agent as a raw traceback, against
   Gate A 4.2's "what rule it broke". `contracts.errors.RuleError` is the base to hang them
   on, and it exists.

7. **F-026/F-027/F-028 — documentation and bookkeeping.** `mcp_server`'s docs were corrected
   in round 1 and `engine`'s in the reconciliation; `viewer/CLAUDE.md` still claims
   `websockets`/`starlette` are not installed (they are). Seven files sit marginally over the
   300-line soft cap without the one required justification line — five of them in
   `contracts/`, where splitting is explicitly disfavoured, so the honest fix is the line and
   not a restructure. 24 entries in `.pipeline/backlog-pass-1.json` are built and green with
   no `status` field.

8. **A contract request the `detail` agent filed and worked around:** `MeshOps` has no
   `replace_mesh(object_id, vertices, faces)`, so `cleanup_bevel_topology` has to
   delete-then-recreate under the same id and therefore declines on any object that has been
   UV unwrapped or carries more than one material slot. Harmless today because detail runs
   before UV; it becomes a real limit the moment anyone re-details a finished asset.
