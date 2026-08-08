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
