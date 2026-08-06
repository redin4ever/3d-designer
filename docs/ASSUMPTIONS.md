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
