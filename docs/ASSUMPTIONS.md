# Assumptions

Every unknown hit during an unattended phase becomes an entry here plus a queued question.
The reversible option wins when the answer cannot be confirmed.

Gate A resolved 48 questions. What follows is what was decided **without** asking — either
because it was derived from an answer the user did give, or because it was too small to spend a
gate slot on. This file is read aloud at the top of Gate B.

---

## A-001 — Python core with in-process `bpy`, rather than a Node orchestrator

- **Phase:** 3 (Gate A close) · **ADR:** [ADR-008](adr/ADR-008-python-core-static-frontend.md)
- **Assumed:** the backend is Python 3.13 importing `bpy` directly; Node is used only for frontend
  tooling and the Puppeteer suite.
- **Why:** the user chose Blender as the engine (9.2) and approved installing the toolchain
  (11.1), but was never asked which language orchestrates. Research had recommended Node
  *because the machine had no Python*; that constraint no longer exists. `bpy` 5.2.0 was verified
  importing in-process, which removes a process boundary from every geometry call.
- **Blast radius:** everything server-side. This is the largest assumption in the file.
- **Reversal cost:** high after Phase 4. Low right now.

## A-002 — Geometry checks report by default rather than block

- **Phase:** 3 · **ADR:** [ADR-005](adr/ADR-005-verification-split.md)
- **Assumed:** checks run after every geometry-changing operation and populate the response, the
  export banner and conflict flags — but do not halt the agent. A runtime setting flips this to
  blocking.
- **Why:** 6.3 chose "export allowed with a warning banner" and 8.1 gave visual judgement the
  decision, so blocking-by-default would contradict both. 11.3 gives measurement authority over
  hard facts, which is honoured by making the measurement decide the *verdict* without it
  halting the *run*.
- **Blast radius:** the check layer's return contract; the operation loop.
- **Reversal cost:** low — it is a config default.

## A-003 — Collision meshes and texture atlasing are not in v1

- **Phase:** 3 · **Assumed:** offered at 12.3 and not selected, so they are backlog items at low
  priority rather than scope.
- **Why:** the user selected LODs and modular snapping pieces from the same list. Reading an
  unselected multiSelect option as "not now" is the literal answer.
- **Blast radius:** export module only.
- **Reversal cost:** low — both are additive.

## A-004 — "Attempt everything" is sequenced by the user's own priorities

- **Phase:** 3 · **Assumed:** 2.3 said nothing is out of scope, but two build passes cannot make
  rigging and organic sculpting good. Work is ordered by what the user said matters — clipping,
  gaps, alignment, detail/realism (2.1), engine-ready export (1.2), environments (1.4) — and
  rigging/organic get whatever depth remains.
- **Why:** flagged to the user at the time and not contradicted. The alternative is spreading
  effort evenly and finishing nothing.
- **Blast radius:** what `docs/HANDOVER.md` contains at the end of the run.
- **Reversal cost:** none — it is a sequencing choice, revisitable at Gate B.

## A-005 — The HTTP transport binds to loopback by default

- **Phase:** 3 · **ADR:** [ADR-009](adr/ADR-009-unrestricted-execution-local-trust.md)
- **Assumed:** ADR-009 gives connected agents arbitrary code execution and full disk access. The
  HTTP listener therefore binds `127.0.0.1` unless an explicit flag says otherwise, and that flag
  logs a warning.
- **Why:** the user chose unrestricted execution and local-machine deployment (7.1, 7.2). Binding
  to all interfaces was not asked for and is not implied by either answer.
- **Blast radius:** one line of server config.
- **Reversal cost:** trivial.

## A-006 — The initial constraint vocabulary

- **Phase:** 3 · **ADR:** [ADR-004](adr/ADR-004-typed-operations-constraint-placement.md)
- **Assumed:** v1 ships `on`, `flush_with`, `centred_on`, `follows`, `offset_from`, `ends_at`,
  `plumb`, `parallel_to`, `perpendicular_to`, `coplanar_with`, `spacing`, `clear_of`. Holodeck
  used 10 predefined constraint types successfully; this is a comparable set biased toward the
  hard-surface and architectural work the user named.
- **Why:** 3.4 chose constraint-first placement but the vocabulary itself was never enumerated to
  the user.
- **Blast radius:** the solver and every operation that takes a placement.
- **Reversal cost:** medium — additive constraints are cheap, renaming existing ones is not.
- **Queued for Gate B:** yes, with evidence of which constraints agents actually reached for.

## A-007 — Checkpoints are retained for the session; the operation log is retained with the scene

- **Phase:** 3 · **ADR:** [ADR-006](adr/ADR-006-undo-and-checkpoints.md)
- **Assumed:** named checkpoints live as long as the session. The operation log is part of the
  scene document and persists with it, so undo survives a reload.
- **Why:** 4.3 chose per-action undo plus named checkpoints but retention was never discussed.
- **Blast radius:** scene document schema.
- **Reversal cost:** low.

## A-008 — 1 Roblox stud = 0.28 metres

- **Phase:** 3 · **ADR:** [ADR-010](adr/ADR-010-export-profiles-roblox-first.md)
- **Assumed:** the Roblox export profile converts at 0.28 m per stud.
- **Why:** the user named Roblox as their usual engine (12.1) but no conversion factor was
  discussed. This is the commonly-cited figure and needs verification against Roblox's own
  documentation during Phase 4, not acceptance on the strength of this note.
- **Blast radius:** the Roblox profile only.
- **Reversal cost:** trivial — one constant.
- **Queued for Gate B:** yes, unless verified in Phase 4.

## A-009 — `pytest` for the backend, Puppeteer for the frontend

- **Phase:** 3 · **Assumed:** both run on this machine today, which is what 9.4 required.
- **Why:** framework choice was never a gate question and neither is user-visible.
- **Blast radius:** test tooling.
- **Reversal cost:** low.

## A-010 — The scene document is JSON

- **Phase:** 3 · **ADR:** [ADR-002](adr/ADR-002-parametric-scene-document.md)
- **Assumed:** the parametric document is JSON on disk — readable, diffable, trivially versioned.
- **Why:** 6.1 chose a parametric working file but not its encoding.
- **Blast radius:** persistence layer; anything that reads a scene file by hand.
- **Reversal cost:** low behind a serialiser interface, which is how it is built.

---

# Gate B reconciliation — 2026-08-06

Every assumption above was read out at Gate B and voted on. This is the outcome. Where an
assumption is amended, the text above stands as the record of what was assumed; this section
is what is true from here.

| id | Outcome | What changed |
|---|---|---|
| A-001 | **Confirmed** | Python core with in-process `bpy` held, and turned out to have window access, so unwrap/bake/export all run in-process. The unused subprocess fallback flag is deleted and `ARCHITECTURE.md` corrected (Gate B 2.3). The reversal window is closed; that is now a stated fact rather than a caveat. |
| A-002 | **Amended** | Per-operation checks still report and never halt the agent. **Phase promotion now blocks** — [ADR-012](adr/ADR-012-phase-promotion-is-a-hard-gate.md), Gate B 1.1. The reporting default applies to operations, not to phase boundaries. |
| A-003 | **Amended** | Read as "not now" from an unselected Gate A option. At Gate B 3.2 the user actively selected collision meshes and texture atlasing, then cut them at 6.1 for budget. They are now **named `HANDOVER.md` items the user wants**, not non-goals. |
| A-004 | **Confirmed, and paid** | Sequencing by the user's own priorities held. The promised honest write-up is `docs/HANDOVER.md`, written this gate — it did not exist before, which was itself the drift Phase 6 found. Rigging and organic sculpting have **zero** coverage, not thin coverage. |
| A-005 | **Confirmed** | HTTP still binds `127.0.0.1` and still warns on any other host, naming ADR-009. The non-loopback path remains untested; that is recorded in `HANDOVER.md`. |
| A-006 | **Still open** | The 12-type constraint vocabulary is built and correct. "Which constraints agents actually reach for" was offered at Gate B 2.4 against measuring scale, and **scale won**. No agent has exercised the vocabulary outside a test file, and none will before the run ends. Goes to `HANDOVER.md` as the one assumption this pipeline could not resolve. |
| A-007 | **Confirmed** | Retention unchanged. The operation log now persists more of each operation — [ADR-015](adr/ADR-015-scene-document-v2.md) — but for the same lifetime. |
| A-008 | **Resolved** | Verify 1 stud = 0.28 m against Roblox's own documentation and pin it with a cited regression test (Gate B 2.1). No longer an assumption after the final pass. |
| A-009 | **Amended** | Puppeteer is installed and the frontend gets a **smoke test** — page loads, canvas draws, log updates — not the full interaction and layout suite chosen at 2.2 and cut for budget at 6.1. Real keyboard behaviour and CSS layout stay unverified, in `HANDOVER.md`. |
| A-010 | **Confirmed** | The scene document is still JSON, now at schema version 2. |

**Six confirmed, three amended, one resolved, one still open.** No assumption was overturned.

---

# point-and-edit — 2026-08-06

Taken during the add-feature run for pointing, priority and direct editing. Each was the
reversible option; each is recorded here rather than asked, because the gate had already closed.

## A-011 — Annotations ride the wire protocol, not the HTTP API

- **Feature:** point-and-edit · **Seam:** `live-http-api`
- **Assumed:** a pointed-at part, its words and its cropped image all travel as one
  `ANNOTATE` client message over the existing viewer WebSocket — not as an HTTP POST to
  `src/app/live.py`'s `/api/*` surface.
- **Why:** `live.py`'s own class docstring draws the line: the HTTP API is for **setup**
  actions, and `contracts.wire` is "for what is happening to the scene". An annotation about
  a part is about the scene. It also keeps every operator action on one ordered channel, so a
  note cannot arrive before the selection it refers to.
- **Blast radius:** `src/contracts/wire.py`, `src/viewer/client.py`, `frontend/src/socket.js`.
- **Reversal cost:** low — the payload is already a dict; moving it to HTTP means changing
  the transport call, not the shape.
- **Caveat filed:** `websockets` defaults to a 1 MB frame limit. A 1024px PNG (Q-23) is
  normally 100–400 KB base64-encoded, but not guaranteed to be. `serve()` must raise
  `max_size` explicitly, and the browser must refuse to send an oversized crop with a
  message rather than having the socket closed underneath it.

## A-012 — The crop is encoded and downscaled in the browser

- **Feature:** point-and-edit · **Seam:** `mcp-images`
- **Assumed:** the browser crops its own canvas, downscales to 1024px on the long edge, and
  encodes PNG. `mcp_server.downscale_image` is not used on this path.
- **Why:** `downscale_image` handles binary PPM only, on purpose — "adding a real codec is a
  gate decision, not a quiet addition" (`mcp_server/CLAUDE.md`). The canvas already produces
  PNG and already resamples; converting PNG→PPM in the browser to feed a Python downscaler
  that would re-encode is work with no benefit. The cost control (ADR-003) is honoured at the
  same 1024px bound, just applied one hop earlier.
- **Blast radius:** `frontend/src/` capture code only.
- **Reversal cost:** low — if a server-side codec ever lands, the browser sends full-size and
  the bound moves back to Python.

## A-013 — Focus is orchestrator state, not an operator note

- **Feature:** point-and-edit · **Seam:** `orchestrator-notes`
- **Assumed:** parts marked important are held as a standing set on the orchestrator and
  re-attached to **every** `ActionReport` until cleared, rather than queued through
  `add_operator_note`.
- **Why:** Q-10 chose "a standing instruction it re-reads every turn". Operator notes are
  drained and cleared on delivery (`reporting.py:187-188`) — correct for a one-off redirect,
  and it would make "focus on this" vanish after one action.
- **Blast radius:** `src/orchestration/reporting.py`, `src/contracts/operations.py`.
- **Reversal cost:** medium — it is a new field on a frozen contract type, so removing it
  means a reconciliation round. Additive and defaulted, so nothing breaks by ignoring it.

## A-014 — Hide/show is browser state, never a scene operation

- **Feature:** point-and-edit · **Seam:** `ops-registry` · **Question:** Q-14
- **Assumed:** hiding a part affects only your own view. It is not logged, not replayed, not
  sent to the agent, and another watcher's view is unaffected.
- **Why:** Q-19 chose one shared history, which makes every logged operation something the
  agent must reason about. "I temporarily moved that out of my way" is not a fact about the
  model, and logging it would put noise into a history whose value is that it describes the
  build.
- **Blast radius:** `frontend/src/` only.
- **Reversal cost:** low — becoming a real operation later is additive.

## A-015 — Direct-manipulation operations live in `src/ops/`

- **Feature:** point-and-edit · **Seam:** `ops-registry`
- **Assumed:** move / rotate / scale / delete / duplicate / rename / set-material are added to
  `src/ops/` beside the 33 existing kinds, rather than to a new `src/edit/` module.
- **Why:** `OPS` is what `scene` replays every logged operation through, and `OP_SPECS` is
  what the registry turns into tool declarations. A second registry would need wiring into
  both, and Q-19's single shared history is exactly the claim that these are ordinary
  operations rather than a separate class of thing.
- **Blast radius:** `src/ops/`, `src/app/handlers.py`, `src/mcp_server/registry.py` counts.
- **Reversal cost:** low — moving a handler between modules is a re-registration.

## A-016 — The feature is built on `build/pass-1`, not a `feat/` branch

- **Feature:** point-and-edit · **Rule:** 5
- **Assumed:** no new branch was cut for this feature.
- **Why:** a second agent is working in this same checkout (its Connect UI is uncommitted in
  `frontend/`). `git switch` moves the working tree for **both** of us, so branching to
  isolate this work would have disrupted theirs. `build/pass-1` is already a non-default
  branch, which is what Rule 5 actually requires.
- **Blast radius:** git history only.
- **Reversal cost:** low — `git branch feat/point-and-edit` after the fact keeps every commit.

## A-017 — Chained move drags keep the earliest rollback point

- **Feature:** multi-selection · **Seams:** `move-release-lifecycle`, `move-pointer-wiring`
- **Assumed:** each released drag sends an absolute position immediately, another axis may
  start from that optimistic position, and rejection restores the position from before the
  first still-unconfirmed drag.
- **Why:** this keeps X-then-Y adjustment responsive without letting a failed first move
  leave later optimistic movement based on a position the build rejected.
- **Blast radius:** `frontend/src/move-gizmo.js`, `frontend/src/point-ui.js`.
- **Reversal cost:** low — waiting for each transform echo can be restored by retaining the
  pending phase as the pointer gate.
## A-020 — Initial built-in texture set

- **Feature:** part-textures
- **Assumed:** ship neutral wood, brick, concrete, stone, metal, and plaster presets.
- **Why:** the user chose built-in presets but did not name a starter set.
- **Blast radius:** preset catalogue only; custom textures and saved material definitions are unaffected.
- **Reversal:** add or remove catalogue records and assets without changing the texture contract.

## A-021 — Texture tools in every mutating phase

- **Feature:** part-textures
- **Assumed:** create, update, and apply textures are legal in blockout, refine, detail, and polish.
- **Why:** texture availability should not disappear when the run changes phase.
- **Blast radius:** MCP role visibility only.
- **Reversal:** narrow the role tuple in the texture tool specs.

## A-022 — Texture import size limit

- **Feature:** part-textures
- **Assumed:** reject individual image files larger than 32 MB.
- **Why:** this bounds accidental memory and browser-transfer cost while covering ordinary 4K PBR maps.
- **Blast radius:** import validation only; existing managed assets remain readable.
- **Reversal:** change one limit constant and its validation tests.

## A-023 — Gable roof is the first semantic roof family

- **Feature:** architectural-quality
- **Assumed:** ship an axis-aligned gable roof operation first; hip, gambrel, mansard and
  curved roofs remain future typed operations.
- **Why:** the incident involved a gable assembled from rotated cubes, and one well-verified
  family is more accurate than a style enum whose branches are only partly correct.
- **Blast radius:** `src/ops/` roof handler, schema and tests.
- **Reversal:** additive — later roof families can be separate operations.

## A-024 — Gable ridges support both world horizontal axes

- **Feature:** architectural-quality
- **Assumed:** `ridge_axis` accepts `x` or `y`; arbitrary yaw is deferred.
- **Why:** this covers rectangular buildings in either grid orientation without introducing
  quaternion input into an architectural tool.
- **Blast radius:** roof geometry and schema.
- **Reversal:** add a direction vector later while retaining the axis values.

## A-025 — Landing stairs are additive

- **Feature:** architectural-quality
- **Assumed:** preserve `add_staircase` exactly and add `add_staircase_to_landing`.
- **Why:** saved operation logs replay by operation kind, so changing the existing handler
  would alter old geometry during undo/reload.
- **Blast radius:** new ops handler and registry entry only.
- **Reversal:** deprecate the old operation after a versioned migration exists.

## A-026 — Landing bounds derive stair placement

- **Feature:** architectural-quality
- **Assumed:** the caller supplies the bottom start point, landing id, tread count and width;
  the tool derives direction, rise and run from live landing bounds.
- **Why:** this moves spatial arithmetic out of the model while keeping the design choice of
  where the stair starts with the model.
- **Blast radius:** landing-stair handler and acceptance queries.
- **Reversal:** add explicit override parameters without changing the default.

## A-027 — Railings remain separate

- **Feature:** architectural-quality
- **Assumed:** landing stairs include stringers but not railings.
- **Why:** `add_railing` is already the verified typed operation for plumb posts, corners and
  clear baluster spacing; duplicating it would create two competing implementations.
- **Blast radius:** stair output only.
- **Reversal:** add a convenience orchestration recipe, not duplicate geometry logic.

## A-028 — Architectural contact stays explicit joinery

- **Feature:** architectural-quality
- **Assumed:** any intentional trim or support penetration is recorded as
  `JoineryIntent`; geometric proximity never implies permission.
- **Why:** the existing clipping model cannot distinguish a socket from a mistake.
- **Blast radius:** operation metadata wiring.
- **Reversal:** none planned; this is an existing product invariant.

## A-029 — No whole-house generator

- **Feature:** architectural-quality
- **Assumed:** fix the missing middle-grain operations rather than adding `build_house`.
- **Why:** ADR-004 records lower execution accuracy for over-composite calls and the user
  explicitly asked to restore the app's purpose.
- **Blast radius:** product scope only.
- **Reversal:** a future high-level recipe can orchestrate the same typed operations.

## A-030 — Real-Blender architectural smoke proof

- **Feature:** architectural-quality
- **Assumed:** geometry contracts run on `FakeEngine`, with one `needs_blender` smoke test
  confirming the same operations render through the real adapter.
- **Why:** fake geometry proves dimensions and topology but not the actual Blender scene path.
- **Blast radius:** ops test suite only.
- **Reversal:** the smoke can move to a broader integration suite later.

## A-031 — Existing staircase replay remains bit-for-bit

- **Feature:** architectural-quality
- **Assumed:** old `add_staircase` parameters and produced ids do not change.
- **Why:** operation logs are the source of truth and silently changing replayed geometry is
  worse than keeping the legacy operation available.
- **Blast radius:** compatibility tests pin the old handler.
- **Reversal:** requires a versioned scene migration.

## A-032 — Chimneys use a neutral masonry assembly

- **Feature:** architectural-quality
- **Assumed:** a house chimney consists of a rectangular masonry shaft, tapered roof
  flashing, an overhanging crown, and one to four cylindrical flues with raised rims.
- **Why:** the reported featureless cube omitted every junction and termination that makes
  a chimney read as designed; this neutral assembly is style-agnostic and material choice
  remains with the caller.
- **Blast radius:** new semantic chimney operation, schema, acceptance and demonstration.
- **Reversal:** all visible dimensions, flue count, and flue wall thickness are explicit
  operation parameters.

## A-033 — Handrail bends share one miter ring

- **Feature:** architectural-quality
- **Assumed:** every top-rail direction change is a true shared miter in one closed shell.
- **Why:** joined closed boxes retain hidden end caps, self-intersect at the bend, and can
  reveal a crack after beveling or numerical changes.
- **Blast radius:** `add_railing` top-rail geometry and persisted defect acceptance.
- **Reversal:** none planned; disconnected rail shells are invalid construction.

## A-034 — Facade ribs split around real wall openings

- **Feature:** surface-mounted-features
- **Assumed:** a rib whose layout crosses a door or window is split into only the solid
  wall segments above, below, or beside that opening; the whole rib is not discarded.
- **Why:** the user reported ribs colliding with the garage doors. Splitting preserves the
  cladding rhythm while making it geometrically impossible for a rib to cover an opening.
- **Blast radius:** the new facade-rib operation and the regenerated factory artifact.
- **Reversal:** low — change the layout policy to omit any rib that meets an opening.

## A-035 — Facade openings receive 50 mm rib clearance

- **Feature:** surface-mounted-features
- **Assumed:** rib segments stop 50 mm short of every opening edge and segments shorter
  than 100 mm are omitted.
- **Why:** exact edge contact can still read as a collision after beveling or export
  quantization; 50 mm is visible construction clearance without disrupting the pattern.
- **Blast radius:** facade-rib validation, geometry, and acceptance tests.
- **Reversal:** low — both values are explicit operation parameters in the public schema.

## A-036 — Impact heads are a semantic middle-grain operation

- **Feature:** model-generation-quality
- **Assumed:** add `add_impact_head`, not a whole-hammer generator and not another primitive.
- **Why:** the reported failure is relational: plates, collars, faces, and sockets must agree. A
  whole weapon would bury too many design decisions in one call; individual primitives preserve
  the failure mode.
- **Reversal:** additive recipes can orchestrate the operation later.

## A-037 — Neutral dual-strike industrial silhouette

- **Feature:** model-generation-quality
- **Assumed:** the first family is a symmetrical dual-strike hammer/maul head. Decorative claws,
  floating fins, and disconnected status panels are excluded from the semantic assembly.
- **Why:** both striking sides then carry the same believable load path and every visible part has
  a mechanical role. Symmetry is a strong neutral default; asymmetrical tools can be separate
  families rather than half-supported branches.
- **Reversal:** add another semantic operation or an explicitly tested style branch.

## A-038 — Fitted armor follows shared dimensions

- **Feature:** model-generation-quality
- **Assumed:** one inset top cap and front/back cheek plates are derived from the body dimensions,
  touch the body directly, and retain a visible reveal around their edges.
- **Why:** independent plate coordinates caused the current floating, poorly aligned top assembly.
  Shared dimensions make misfit unrepresentable.
- **Reversal:** expose a plate-layout enum after a second verified layout exists.

## A-039 — Mechanical joints carry explicit load paths

- **Feature:** model-generation-quality
- **Assumed:** each striking face sits on a shoulder that sockets into the body; the handle enters a
  dedicated underside socket. Intentional insertion depths become `JoineryIntent` records.
- **Why:** a disk touching the side of a box has no convincing way to transfer impact. Shoulders,
  collars, and sockets explain assembly and distinguish designed overlap from clipping.
- **Reversal:** all insertion dimensions are public parameters.

## A-040 — Invalid proportions are rejected atomically

- **Feature:** model-generation-quality
- **Assumed:** every visible dimension is explicit. Validation rejects plates that cannot fit,
  sockets wider than the body, non-positive reveals, and shoulders/faces with impossible nesting;
  it never silently rescales one part.
- **Why:** silent correction hides the same proportion mistakes the tool is intended to prevent.
- **Reversal:** convenience presets can supply explicit parameter sets above this contract.

## A-041 — Parts stay separate and predictably named

- **Feature:** model-generation-quality
- **Assumed:** body, top plate, cheek plates, shoulders, collars, strike faces, rims, and handle
  socket remain separate mesh objects with deterministic ids. Materials are assigned afterward.
- **Why:** the generator needs different metal, ceramic, and energy materials, while stable ids let
  agents address parts without rediscovering them visually.
- **Reversal:** callers may join parts after material assignment or export.

## A-042 — Fit is an automatic REFINE-phase acceptance gate

- **Feature:** model-generation-quality
- **Assumed:** `add_impact_head` is a REFINE tool. Zero-gap checks cover top/cheek plates, both
  shoulder/body joints, both collar/face joints, and the handle socket/body joint; positive-volume
  checks cover representative structural parts.
- **Why:** these are the exact relationships that were visibly wrong, and the project already
  blocks phase promotion on persisted acceptance failures.
- **Reversal:** tolerances and the role tuple are local registry/acceptance changes.

## A-043 — The existing hammer is the real-Blender regression artifact

- **Feature:** model-generation-quality
- **Assumed:** preserve primitive compatibility, rebuild only the head section through
  `add_impact_head`, remove the old free-floating plates/claws/fins, render it in Blender, and
  inspect the image before completion.
- **Why:** unit geometry can prove fit but not whether the assembled silhouette reads well.
- **Reversal:** the generator remains an ordinary script and can evolve independently.

## A-044 — Striking faces use replaceable socketed inserts

- **Feature:** model-generation-quality
- **Assumed:** each broad striking face carries a smaller, darker wear insert inside the retaining
  rim. The insert has explicit diameter, exposed depth, and socket depth.
- **Why:** the first real render proved that a structurally fitted but featureless reflective disk
  still reads as under-designed. A replaceable wear part gives the face hierarchy and a functional
  reason for its material break.
- **Blast radius:** impact-head schema, geometry, acceptance, joinery, and hammer materials.
- **Reversal:** remove the three striker parameters and two deterministic parts.

## A-045 — One reusable profiled-solid tool

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** add one `add_profiled_solid` REFINE operation whose ordered 2D sections cover
  both straight extrusion and variable-section lofting.
- **Why:** one middle-grain tool replaces brittle primitive stacks without adding separate
  extrusion, loft, taper and horn tools to an already-large visible catalogue.
- **Blast radius:** operation registry, validation, acceptance, wiring, documentation.
- **Reversal:** split the schema into narrower tools while retaining the geometry kernel.

## A-046 — Explicit local sections, no inferred proportions

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** callers supply an origin, a world axis, and at least two ordered stations. Each
  station supplies its axis offset and an ordered closed 2D profile in metres.
- **Why:** local sections reduce a 3D shape to auditable dimensions and correspondence. Hidden
  presets would recreate the unreported proportion choices that produced the weak forge.
- **Blast radius:** schema, JSON validation, generator scripts.
- **Reversal:** add named presets above this explicit contract later.

## A-047 — Closed convex profiles are the safe first kernel

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** profiles must be convex, consistently wound, non-self-intersecting, have equal
  vertex counts, and stations must increase strictly. Ends are capped, producing one closed solid.
- **Why:** arbitrary concave loft correspondence is ambiguous and can create folded faces. A
  convex closed kernel covers anvils, hoods, brackets, handles and tapered fixtures reliably.
- **Blast radius:** geometry builder and named validation errors.
- **Reversal:** add triangulated concave profiles after a tested correspondence policy exists.

## A-048 — Structural errors reject atomically

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** malformed winding, repeated points, crossing edges, station reversals, impossible
  bevels and degenerate sections reject before any object is created. Visual styling remains the
  agent's decision and is not silently corrected.
- **Why:** a partial or silently rescaled mesh is harder to repair than a precise refusal naming
  the station and rule.
- **Blast radius:** validation, tests, action reports.
- **Reversal:** convenience correction can be an explicit opt-in operation later.

## A-049 — Topology and declared bounds are acceptance gates

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** runtime acceptance requires positive volume and forbids boundary holes,
  non-manifold edges/vertices, loose geometry, flipped normals and self-intersections. Unit and
  Blender tests separately pin exact bounds against the supplied stations.
- **Why:** those facts are machine-measurable and directly affect export; aesthetic realism is
  not honestly decidable by geometry checks.
- **Blast radius:** acceptance declarations and Blender regression coverage.
- **Reversal:** add component-wise dimension acceptance if tuple metrics gain comparison support.

## A-050 — Assemblies remain editable and materials stay separate

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** each operation creates one deterministic mesh, while a scene may compose several
  profiled solids as separate fitted parts. The tool does not auto-join or assign materials.
- **Why:** the forge needs distinct face, body, horn, hood and wear materials, and stable object
  ids allow later measurement and correction.
- **Blast radius:** operation result shape and forge generator.
- **Reversal:** callers can join selected parts explicitly before export.

## A-051 — Realistic silhouette with game-ready density

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** the rebuilt forge prioritizes historically plausible proportions and readable
  construction while keeping section counts deliberate rather than subdivision-heavy.
- **Why:** the reported problem is realism and incorrect construction, not lack of raw polygon
  count. More triangles would preserve the same wrong silhouette.
- **Blast radius:** forge station data, materials, render and GLB size.
- **Reversal:** a cinematic variant can add subdivision and texture displacement afterward.

## A-052 — Forge regression targets the hero silhouette and airflow path

- **Feature:** profiled-shape-design-accuracy
- **Assumed:** rebuild the anvil as a continuous profiled load-bearing form and the hood as a
  tapered collector into the chimney; retain the surrounding editable set, then re-render and
  inspect the whole composition.
- **Why:** those are the largest visible failures in the current render and exercise both
  variable-section horizontal and vertical lofting.
- **Blast radius:** blacksmith generator and its regression test.
- **Reversal:** the generator remains declarative and can replace additional props incrementally.

## A-053 — Robust local collaboration is the product boundary

- **Assumed:** dependable local launch-to-export collaboration; cloud, multi-writer, new-format,
  and Blender-replacement work stays outside this pass.

## A-054 — One responsive command layout down to 529px

- **Assumed:** one responsive command layout, tested without overlap from 529px upward.

## A-055 — Sidebar sections contain their own growth

- **Assumed:** flexible chat plus bounded, internally scrolling inspectors and logs.

## A-056 — Automatic detection, truthful state, explicit external writes

- **Assumed:** detect readiness automatically, require a click for external config writes, and
  report restart-required until the client is reloaded.

## A-057 — Scene replacement pauses safely; exports are explicit

- **Assumed:** scene replacement pauses and stays paused; export defaults to the whole scene.

## A-058 — Blender work stays asynchronous to users but synchronous to Blender

- **Assumed:** keep async jobs while dispatching Blender callbacks to its owning thread, proven
  by real project/GLB round trips.

## A-059 — Phase-focused MCP discovery replaces the 52-tool flat list

- **Assumed:** phase-focused discovery, compatible authorization, and explicit raw opt-in.

## A-060 — Agents receive a short mandatory verification loop

- **Assumed:** orient, build semantically, inspect/measure/repair, then promote on acceptance.

## A-061 — Accuracy and robustness are evaluated as workflows

- **Assumed:** deterministic workflow evals plus one gate that distinguishes failures from
  unavailable prerequisites.

## A-062–A-085 — Responsive native model import

- **Feature:** responsive-blend-import
- **Assumption IDs:** A-062, A-063, A-064, A-065, A-066, A-067, A-068, A-069, A-070, A-071, A-072, A-073, A-074, A-075, A-076, A-077, A-078, A-079, A-080, A-081, A-082, A-083, A-084, A-085
- **Details and reversal costs:** [feature assumptions](features/responsive-blend-import/assumptions.md).

- **A-086–A-104 — Contextual file dialog controls:** feature `contextual-file-dialog-controls`; IDs A-086, A-087, A-088, A-089, A-090, A-091, A-092, A-093, A-094, A-095, A-096, A-097, A-098, A-099, A-100, A-101, A-102, A-103, A-104; [details and reversal costs](features/contextual-file-dialog-controls/assumptions.md).

- **A-105–A-123 — Blender import repair:** feature `blend-import-verification`; IDs A-105, A-106, A-107, A-108, A-109, A-110, A-111, A-112, A-113, A-114, A-115, A-116, A-117, A-118, A-119, A-120, A-121, A-122, A-123; [details and reversal costs](features/blend-import-verification/assumptions.md).
