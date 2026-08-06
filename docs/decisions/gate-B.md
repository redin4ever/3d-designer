# Gate B — decisions

The last gate. Six waves, 24 questions, every one carrying evidence from the Phase 6 review
(`docs/research/review-1/`). Nothing here was asked at Gate A; everything here was raised by
looking at what got built.

Answered 2026-08-06. The frame stated at the top of the gate: **one build-and-QA pass
remains, and it holds roughly twelve items.**

---

## Wave 1 — Drift

Where the build diverged from Gate A, with the built behaviour offered first because it
already exists.

### 1.1 — Phase promotion

> Promotion was meant to happen when a phase's acceptance queries pass against live geometry.
> What got built passes as soon as any operation happened at all.

**Chosen: wire the real check, with no force override.** A phase will not advance until its
geometry actually passes.

This is the strictest of the four options. It creates two conflicts, both recorded rather
than silently softened:

- **Against A-002** ("checks report, they do not block"). Promotion now blocks. A-002 is
  amended, not overturned — per-operation checks still report and never halt; only the phase
  boundary blocks.
- **Against Gate A 4.4** (fully autonomous, never stopping). An unpassable query strands an
  unattended agent with nobody to redirect it.

Mitigation, taken as part of the decision: every failing acceptance query must name the exact
object, the exact measured value, the exact threshold, and the operation that would fix it.
A gate an agent cannot get through is only acceptable if it also says how. See
[ADR-012](../adr/ADR-012-phase-promotion-is-a-hard-gate.md).

### 1.2 — Save and reload

> Reloading a scene keeps the geometry and drops every constraint, joinery intent and
> acceptance query — so a wall no longer drags the railing constrained to it.

**Chosen: extend the format, with a schema version bump.** Any file already written loads
with an explicit warning that its constraints were never stored, rather than loading silently
and behaving oddly. See [ADR-015](../adr/ADR-015-scene-document-v2.md).

### 1.3 — The live view

> The 3D view, action log, cadence menu and pause/rollback/redirect are all built and tested,
> and `forge3d serve` never starts the socket a browser would connect to.

**Chosen: start it automatically with the server.** No flag, no second command.

### 1.4 — Built-in dimensions

> Gate A 6.4 chose that the tool never carries real-world dimensions. `add_railing` defaults
> post, baluster and rail cross-sections to 5 cm/5 cm/3 cm.

**Chosen: keep the defaults, report them per call.** Every response says explicitly which
dimensions the tool supplied rather than the agent, so the agent can see and correct them.
The convenience stays; the hidden part goes.

---

## Wave 2 — Assumptions

Last vote on the open assumptions, with the assumed answer offered first.

| | Question | Chosen |
|---|---|---|
| 2.1 | A-008: 1 Roblox stud = 0.28 m, never verified | **Verify against Roblox's own documentation**, pin with a cited regression test |
| 2.2 | A-009: Puppeteer declared, never installed; nothing has run in a browser | **Install it and write the real browser suite** — later reduced to a smoke test at wave 6 for budget |
| 2.3 | A-001 held; the subprocess fallback beside it is an unused `raise` | **Delete the flag**, correct `ARCHITECTURE.md` |
| 2.4 | "Thousands of objects" was never measured past ~900 | **Measure to a real few thousand.** A-006's "which constraints do agents actually reach for" was the alternative and was not chosen — it stays open |

---

## Wave 3 — Gaps

The only multi-select wave, capped at three additions.

### 3.1 — Which unreachable capability to wire (cap: 3)

**Chosen: all three of** `measure` as MCP tools, `inspect` + `promote` tools, and
`detail`/bevel as MCP tools.

That is the entire reader half of the many-readers-one-writer model, plus the phase machinery
an agent needs to advance and finish, plus the detail pass named first-class at Gate A 8.4.
The fourth option — a `joinery` parameter on socket-making operations — was not selected;
B-00K therefore remains open and goes to `HANDOVER.md`.

### 3.2 — New ground

**Chosen: a render/screenshot tool, and collision meshes + texture atlasing.**
**Both subsequently cut at wave 6** as the two additive items that block nothing else. They
are named HANDOVER items the user actively wanted, not non-goals — this is an amendment to
A-003, which had read them as "not now" from an unselected Gate A option.

### 3.3 — The tool-count budget

> Every tool added pushes a role past the 5–8 visible-tools band the research found
> accuracy-optimal.

**Chosen: let roles exceed 8 and measure it.** Ship what is needed, record actual role sizes,
and treat the band as guidance derived from other systems rather than as law here. The
measurement itself is part of the pass, so the next person has evidence rather than a rule.

### 3.4 — Bevel quality

> Real bevels produce mean triangle aspect ratio ~116 on a simple tread — slivers.

**Chosen: tune the bevel and add a cleanup pass.** Closes B-00L.

---

## Wave 4 — Rough edges

Each asked as a preview of the current behaviour against the proposed one.

| | Question | Chosen |
|---|---|---|
| 4.1 | `export_scene` is a registered tool with no handler; it raises a raw `KeyError` | **Direct `ToolSpec.handler`, outside the undo log** — matches what the code was already structured for, and keeps non-geometry actions out of the operation history. [ADR-014](../adr/ADR-014-export-outside-the-operation-log.md) |
| 4.2 | The automatic check never checks neighbours, while every report says it did | **Actually check neighbours.** The spatial index exists for this; 480 pairs took 14 ms, so this was never a performance decision |
| 4.3 | One `add_railing` returns ~3,400 tokens of per-object detail | **Summarise above a threshold** — per-object while it is a handful, aggregate plus defects beyond that |
| 4.4 | Two tool catalogs; the one `tools_for` serves is fiction | **Delete it and delegate to the real registry** |

---

## Wave 5 — Surprises

Behaviour nobody specified, found only by running the product.

| | Question | Chosen |
|---|---|---|
| 5.1 | 0.006 s to create a sphere, 6.5 s for the check that then runs automatically | **Prune it with the spatial index.** Fix the cause, not the symptom; the neighbour checks added at 4.2 get the same benefit. The default cadence stays where Gate A 3.1 put it |
| 5.2 | Undo is session-fatal once the log touches an object it did not create | **Both — reject where we can, survive where we cannot.** Immediate named rejection when the target is knowably foreign, plus a resilient rebuild for anything that slips through. The only option under which both the fresh-scene and open-an-existing-`.blend` workflows survive |
| 5.3 | Undo across a raw-execution barrier re-runs the script instead of restoring | **Restore from the snapshot.** Half of this is already built and paid for; only the read side is missing. Makes `SECURITY.md`'s claim true |
| 5.4 | Only one exception type is caught at the boundary, so geometry failures reach the agent as raw tracebacks | **Both — catch broadly and validate earlier.** A broad catch as the floor so nothing escapes unnamed, plus cheap degeneracy checks in parameter validation so the good cases never reach it |

---

## Wave 6 — Scope the final pass

### 6.1 — The cut

23 items chosen against roughly 12 slots.

**Chosen: cut the two new-ground items, and reduce the browser suite to a smoke test.**
The render/screenshot tool and collision meshes + atlasing go to `HANDOVER.md`; Puppeteer is
installed and asserts the page loads, the canvas draws and the log updates, without a full
interaction and layout suite.

This leaves roughly 19 items against ~12 slots. **Knowingly oversubscribed.** The backlog is
strictly priority-ordered for that reason, and anything not reached becomes a written known
issue with a repro rather than a stub.

### 6.2 — What must be excellent

**Chosen: the multi-agent guarantee actually holds.** Single writer, many readers,
phase-locked, proven under genuine OS concurrency rather than sequential calls in one process.

This is the safety property every other part of the design assumes and the one with zero
evidence behind it today — the lock tests contain no threads at all. It is the top of the
final backlog and it is what the pass is judged on.

### 6.3 — What to stop doing

> `dispatch` decides what an agent may call purely from the role string that agent passes
> with the call. It never checks that against the session's phase or against who is calling.

**Chosen: stop trusting the caller's claimed role.** Role binds to the write lease the agent
holds, and is checked against the current phase. An out-of-phase or unheld-role call is
refused with a named rule. This is what makes the staged plan real rather than advisory, and
it is what makes 1.1's hardened phase gate mean anything. See
[ADR-013](../adr/ADR-013-role-bound-to-lease.md).

### 6.4 — Leftovers and unrecoverable process evidence

**Chosen: do the cheap ones, document the rest.** Write `HANDOVER.md`, correct the four stale
module docs, add the missing guard that makes a duplicated helper loop forever if called
directly, and justify the seven files marginally over the soft cap.

The gate's tests-first matcher is **not** being taught to read combined-scope commits — that
option was offered and not chosen. The summary will state plainly that ten modules have RED
commits the gate cannot parse, six have none at all, and `app`'s tests were committed after
its implementation. No retroactive commits will be fabricated; a green gate bought that way
is worth less than a red one that tells the truth.

---

## What this gate produced

- 5 new ADRs: [012](../adr/ADR-012-phase-promotion-is-a-hard-gate.md),
  [013](../adr/ADR-013-role-bound-to-lease.md),
  [014](../adr/ADR-014-export-outside-the-operation-log.md),
  [015](../adr/ADR-015-scene-document-v2.md),
  [016](../adr/ADR-016-canvas2d-renderer.md)
- `docs/ASSUMPTIONS.md` reconciled — 6 confirmed, 3 amended, 1 resolved, 1 still open
- `.pipeline/backlog.json` rewritten as the final pass scope only, priority-ordered
- `docs/HANDOVER.md` — everything raised and not taken
