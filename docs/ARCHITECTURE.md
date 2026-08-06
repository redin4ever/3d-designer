# Architecture

Decided by a panel of three independent architects at Phase 4.1, judged on disjoint paths, graph
depth, whether any two modules need each other's internals, and how many modules one real journey
touches. Architect 3's decomposition won; two grafts were taken from the others. See
`docs/PIPELINE-LOG.md` for the panel result.

## The one seam everything else hangs off

**`engine` is the only module permitted to `import bpy`.** Every other module is written against
`EngineProtocol`, frozen in `src/contracts/`, and receives a concrete or fake implementation
injected at the composition root.

This has three consequences worth stating plainly:

1. **The entire decision layer is testable with no Blender.** `measure`, `constraints`, `ops`,
   `align`, `gaps`, `detail`, `uv`, `scene`, `orchestration`, `export`, `mcp`, `viewer` all run
   their full pytest suite against `FakeEngine`. Only `engine`'s own tests need real `bpy`.
2. **`dependsOn` governs integration order, not start order.** Because every module compiles
   against frozen protocols rather than against its dependencies' implementations, the whole set
   can be built in parallel. The 7-deep dependency chain is a merge ordering, not a build queue.
   *This only holds if `contracts/` is genuinely complete before fan-out* — which is why the
   contract review at 4.2 is a barrier.
3. **A Blender version bump touches one module's internals**, not fifteen call sites. Given
   Blender ships breaking Python API changes with no deprecation policy (ADR-001), this is the
   difference between a scheduled cost and an unbounded one.

## Directory map

```
src/
  contracts/       frozen shared surface — types, protocols, schemas. MAIN AGENT ONLY.
  testing/         FakeEngine — a real in-memory EngineProtocol, not a mock. MAIN AGENT ONLY.
  engine/          the only bpy importer. Mesh CRUD, modifiers, UV/bake, glTF. In-process only.
  spatial/         maintained BVH; broad-phase nearby-pair and region queries.
  measure/         all 7 metric queries + all 8 defect classes, incl. clipping. Pure, no mutation.
  constraints/     the 12-type constraint vocabulary, resolved to concrete transforms.
  ops/             construction library — primitives, staircase, railing, wall, floor, opening,
                   array-along-curve, LOD chains, modular grid kits.
  align/           quaternion-correct parallel / perpendicular / coplanar / plumb / flush.
  gaps/            repair — fill hole, weld, recalc normals, merge shells, close visual gaps.
  detail/          realism passes — heuristic bevel, surface detail, material variation.
  uv/              UV seam decision, unwrap, PBR bake. Runs in-process — bpy has window access here.
  scene/           the operation log: append, deterministic replay, per-op cache, undo, checkpoints.
  orchestration/   phase state machine, single-writer arbitration, conflict flagging,
                   check cadence policy, and assembly of the standard action report.
  export/          per-engine profiles (Roblox/Unity/Unreal/Godot), budget check, warning banner.
  raw/             arbitrary Python execution against a live engine context. ADR-009.
  viewer/          Python WebSocket server; scene-change events → wire protocol; operator controls.
  mcp_server/      both transports; role-partitioned tool registry; routing.
  app/             THE COMPOSITION ROOT. Builds and wires everything; owns the
                   JSON→domain parameter coercion at the agent boundary.
  forge3d_cli.py   the `forge3d` entry point: `doctor` and `serve`.
frontend/          static ES-module page + node:test suite. Node toolchain, no Python.
```

## Data flow through one request

An agent calls `add_railing(path=stair.outer_edge, height=0.95, baluster_gap=0.09)`:

```
mcp            validates params against the frozen ToolSpec; identifies the calling role
  ↓
orchestration  is this role the current writer? is this operation legal in this phase?
  ↓            acquires the write lock
scene          appends the operation to the log (not yet evaluated)
  ↓
ops            decomposes "railing" into posts, top rail, bottom rail, balusters
  ↓
constraints    resolves `follows`, `plumb`, `spacing`, `ends_at` against current geometry
  ↓            → concrete transforms
engine         executes the resulting mesh/transform primitives against live bpy
  ↓
scene          caches the resulting MeshSnapshot per operation
  ↓
spatial        updates the BVH for the changed objects
  ↓
measure        runs the metric queries and defect checks, scoped to changed objects + neighbours
  ↓
orchestration  assembles "what changed + key measurements + new problems" (Gate A 4.1)
  ↓            applies the cadence policy (Gate A 3.1) and the report-vs-block setting
  ├──────────→ mcp returns the report to the agent
  └──────────→ scene emits SceneChangeEvent → viewer → WebSocket → frontend highlights the change
```

The write lock is released at the end. Read-only sub-agents may call `measure` throughout without
taking it (ADR-007).

## Why the seams are where they are

**`constraints` is its own module, not part of `ops`.** Three callers need it — `ops`, `align`,
`gaps` — plus `scene` re-solves constraints when an upstream anchor moves (ADR-002's "move the
stair and the railing follows"). Folding it into `ops` would mean every operation reimplements or
imports around the same dependency-graph, cycle-detection and quaternion math.

**Measurement is one module, not eight.** The 7 metric queries and 8 defect classes share the same
`MeshSnapshot` input, have no independent internals, and Gate A 4.1 wants *one* report field
("new problems"), not results polled from eight places. Clipping detection in particular is listed
in ADR-005's own decision table alongside manifold and scale as one row of "decided by
measurement". Internally it splits one file per defect class and per metric group, so two agents
extending different checks never touch the same file.

**`spatial` is separate from `measure` for a different reason** — not decision content but test
discipline. ADR-011 says getting BVH invalidation wrong is a silent-wrong-answer failure and needs
direct tests, not integration coverage. A structure with an invalidation contract is a different
actor from a pure computation.

**`gaps` owns repair, `measure` owns detection.** Backlog B-004 (detect) and B-011 (taxonomy +
repair) overlap almost word for word; the detection half is absorbed into `measure` so there is
exactly one detector, and `gaps` owns only the corrective half. Detection is a pure function,
repair is a mutation — a distinct actor.

**`orchestration` merges phase gating and sub-agent coordination** because ADR-007 says outright
that phase gating *is* the concurrency-control mechanism. Two names, one mechanism. It also owns
the check-cadence policy and report assembly — two of the three architects independently placed
that policy here rather than in the measurement layer, because cadence and report-vs-block are
policy decisions with three call sites (`scene`, phase promotion, `export`), not geometry maths.

**`export` requests glTF bytes from `engine`** rather than serialising glTF itself. One architect
proposed a custom writer over cached buffers for testability; rejected, because Blender's own
exporter handles PBR and material edge cases that would otherwise have to be reimplemented
correctly. Testability is preserved instead by keeping the *conversion* (axis, handedness, unit,
budget) in `export` as pure functions over plain data, with round-trip fixtures that need no
Blender.

**`viewer` and `frontend` are separate modules** despite being one feature. Different languages,
different toolchains, different test suites (pytest vs Puppeteer), and therefore different owners
under Rule 5. `frontend` depends only on the WebSocket wire-protocol contract, so its Puppeteer
suite runs against fixtures with no Python and no Blender.

**`scene` never imports `viewer`.** `scene` exposes `subscribe(listener)` and emits a
`SceneChangeEvent` typed in contracts; `viewer` is the only subscriber, wired at the composition
root. The dependency arrow points from the web layer into the core and never back.

**`raw` is deliberately tiny and isolated.** It is the one module whose entire job is the
capability ADR-009 accepted with the risk stated. Small enough to get its own security review
rather than being reviewed inside a larger diff. It acquires the same write lock as any other
mutation, and every call is logged as an opaque, non-replayable undo barrier.

## The dependency graph

```
contracts ──── (everything compiles against this)

engine ── spatial ── measure ── constraints ─┬─ ops ──┐
                        │                    ├─ align ─┤
                        │                    └─ gaps ──┤
                        │                              ├── scene ── orchestration ── mcp
                        │              detail ─────────┤                    │
                        │              uv ─────────────┘                    │
                        │              raw ─────────────────────────────────┤
                        └────────────── export ────────────────────────────┘
                                                        viewer ── (subscribes to scene)
frontend  (depends only on the wire-protocol contract)
```

Longest chain: `engine → spatial → measure → constraints → ops → scene → orchestration → mcp`.
Seven hops, all real layering with no pass-through wrappers. It does not serialise the build
because of the protocol seam described at the top of this file.

## What stays with the main agent

`src/contracts/`, `.pipeline/*.json`, `pyproject.toml`, root config, the composition root that
wires dependencies, and every integration decision. Rule 5.

## Corrections made during the build

Four things this document asserted turned out to be wrong once real code existed. They are
recorded rather than quietly edited, because each was found by something specific and
knowing what found it is worth as much as the correction.

**`src/mcp/` had to become `src/mcp_server/`.** The package name shadowed the `mcp` PyPI SDK
that `pyproject.toml` depends on. The root `conftest.py` puts `src/` first on `sys.path`, so
`import mcp` from inside our own transport code resolved back to us and the SDK was
permanently unreachable — meaning no subscription client could ever have connected, the one
thing Gate A 7.4 asked for. Found by the module's own author, who correctly reported it as
unfixable from inside the module's own boundary.

**`ToolRole.REFINE` was over-subscribed.** `ops`, `gaps` and `align` each correctly declared
`REFINE`; together that was 19 tools against a load-bearing 8-tool bound, and the registry's
fair-cap fallback was silently hiding `repair`, `make_plumb` and `close_visual_gap` — core
operations. The cap was the symptom, not the fix. `REPAIR` and `ALIGN` are now separate
roles inside the same phase, and every role sits within 1–8 with nothing hidden.

**`ScenePort.document` was declared a method; `Scene` exposes a property.** Both consumers
matched the declaration, and both wrote test doubles that matched it too — so three suites
were green while the real trio could never have worked together.

**Nobody owned JSON→domain conversion.** `ops` documented, correctly, that params carry
`Vec3` internally and that converting from the wire shape "is `scene`'s or `mcp`'s job at
the boundary". Every module honoured that. Nobody built the boundary, so every point-taking
operation raised `AttributeError: 'list' object has no attribute 'x'` the first time a real
agent called it. It now lives in `app/handlers.py`, driven by each tool's own declared
schema — a structural guess would have turned `add_lod_chain`'s `ratios=[0.5, 0.25, 0.1]`
into a coordinate.

The pattern in all four: a module can be entirely correct in isolation and still not
connect. Two of the four could only ever have been found by putting the real objects side by
side, which is what `src/app/` and its end-to-end suite exist to do.
