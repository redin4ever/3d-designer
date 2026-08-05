---
name: build-product
description: Fixed-length pipeline for building a web product — researches the idea and its competitors, prepares DESIGN.md candidates for the user to choose from, asks every pre-build question in one exhaustive gate, builds it modularly test-first with parallel agents, runs background QA agents across a backend suite and a Puppeteer frontend suite, then researches what actually got built and asks a second, evidence-driven set of questions before one final build-and-QA pass. Use when starting a new web app or site from an idea, or when resuming an interrupted run.
argument-hint: "<product idea>" [--design <slug|path|url>] | resume | status | iterate
---

# Build Product

A nine-phase, **fixed-length** pipeline that turns an idea into a tested, documented,
modular web product.

The defining constraint: **the user is reachable only at Phase 3 and Phase 7.** Everything
else runs unattended. Read [.claude/rules/autonomy.md](rules/autonomy.md) before any
unattended phase and treat it as binding.

## The pipeline

```
0 Bootstrap
   ↓
1 Research the idea → 2 Design candidates → 3 GATE A  ← every question
   ↓
4 Build → 5 QA
   ↓
6 Research what got built  ← same shape as phase 1, pointed at the product
   ↓
7 GATE B  ← only what phase 6 discovered
   ↓
8 = 4 Build + 5 QA, once more → docs/PIPELINE-SUMMARY.md → stop
```

Phases 1, 2, 4, 5, 6, 8 are unattended. Phases 3 and 7 are the only gates.

**Gate A gets every question.** Everything answerable before code exists is asked there —
Gate A is not a first instalment, it is the whole pre-build conversation.

**Gate B is earned, not scheduled.** Phase 6 is a research phase, run exactly like Phase 1
but pointed at the built product: it checks what the thing *actually does*, as opposed to
what it was asked to do. Gate B then asks only what that research turned up. A Gate B
question with no Phase 6 evidence belonged at Gate A and does not get asked.

**Two build passes, then it stops.** Phase 8 repeats phases 4 and 5 exactly once and the
run ends — no loop, no exit condition to evaluate. Anything outstanding goes to
`docs/HANDOVER.md` rather than getting half-built. Say this at Gate A: a user who thinks
they get three chances answers differently from one who knows they get two.

## Run to the next gate — do not stop between phases

**One invocation runs from where it starts to the next gate, in a single turn.**

Phases are checkpoints for resuming after a crash, not turn boundaries. When a phase's
exit conditions are met, read the next phase file and begin it immediately. Do not report
and wait; do not say "Phase 4 complete, shall I continue"; do not end the turn because a
natural summary presented itself. Nobody is there to read it — that is the premise.

Only three things hand control back: a question wave at Gate A or Gate B, the end of the
run after `docs/PIPELINE-SUMMARY.md`, or an escalation
([rules/autonomy.md](rules/autonomy.md)).

| From | Runs to | Handing back at |
|---|---|---|
| Invocation | Phases 0 → 3 | the Gate A waves |
| Gate A answered | Phases 4 → 7 | the Gate B waves |
| Gate B answered | Phase 8, then the summary | the end of the run |

If that feels long, it is meant to. Stopping midway is the failure this pipeline exists
to prevent.

### The one way this breaks that willpower cannot fix

Spawning a wave of agents **in the background** ends the turn — not because you chose to
stop, but because you have handed the work away and polling for it is forbidden. There is
then nothing left to do, and stopping is the only legal move.

So every wave this pipeline spawns passes `run_in_background: false`. It defaults to
**true**, so leaving it out is choosing to stop. Concurrency comes from putting many tool
calls in one message, not from backgrounding — you get the parallelism either way, and only
one of them keeps control. See
[agent-briefs.md](references/agent-briefs.md#concurrency--parallel-and-background-are-not-the-same-thing).

## The gate

```bash
node .pipeline/check.mjs      # exit 0 = the run's own exit conditions hold
```

Phases 4 and 5 end here rather than on a self-report. It checks what is on disk — module
statuses, the journal for units that started and never ended, commit order for whether the
tests could ever have failed, file sizes, the decision records — and runs both suites.
Details and the meaning of exit 2 are in
[pipeline-state.md](references/pipeline-state.md#the-gate).

Green means *the run did what it says it did*. It does not mean the product is right; that
is what the module reviewer and the two gates are for.

## Phase index

Read a phase file when you enter that phase. Do not preload them.

| # | Phase | Attended | Read |
|---|-------|----------|------|
| 0 | Bootstrap / resume | — | [references/pipeline-state.md](references/pipeline-state.md) |
| 1 | Research the product and its neighbours | no | [references/phase-1-research.md](references/phase-1-research.md) |
| 2 | Take the user's DESIGN.md, or prepare candidates for them | no | [references/phase-2-design.md](references/phase-2-design.md) |
| 3 | **Gate A** — every question; the user picks the design | **yes** | [references/phase-3-gate-a.md](references/phase-3-gate-a.md) |
| 4 | Build — contracts, TDD, parallel agents, docs | no | [references/phase-4-implementation.md](references/phase-4-implementation.md) |
| 5 | QA — background agents, two suites | no | [references/phase-5-qa.md](references/phase-5-qa.md) |
| 6 | Review research — what the built product actually does | no | [references/phase-6-review.md](references/phase-6-review.md) |
| 7 | **Gate B** — the last gate; only what Phase 6 found | **yes** | [references/phase-7-gate-b.md](references/phase-7-gate-b.md) |
| 8 | Repeat 4 and 5 **once**, then write the summary and stop | no | [phase-4](references/phase-4-implementation.md) then [phase-5](references/phase-5-qa.md) |

Supporting references, read on demand:

- [references/parallelism.md](references/parallelism.md) — the fan-out model: the ready queue, the only three real barriers, and the four verification agents. **Read before Phase 4.**
- [references/design-md-catalog.md](references/design-md-catalog.md) — the 74 fetchable DESIGN.md systems and their URLs
- [references/puppeteer-harness.md](references/puppeteer-harness.md) — frontend suite structure and conventions
- [references/agent-briefs.md](references/agent-briefs.md) — the prompt shape every spawned agent gets
- [references/scaling-large-codebases.md](references/scaling-large-codebases.md) — hierarchical CLAUDE.md, `.claudeignore`, hooks, codebase maps, LSP/MCP, packaging

## Invocation

| Argument | Behaviour |
|---|---|
| `"<idea>"` | Fresh run from Phase 1. Refuses if `.pipeline/state.json` exists — use `resume`. |
| `--design <slug\|path\|url>` | The user's design system. Skips candidate selection entirely; Phase 2 just validates and adopts it. A root `DESIGN.md` that already exists does the same thing without the flag. |
| `resume` | Read state, re-enter the recorded phase, continue. |
| `status` | Print state, pass number, backlog size, suite status. No work. |
| `iterate` | A **user-requested** extra pass on a finished run: Phase 6 review, Gate B, then one more build and QA. Only ever run when asked for by name — the pipeline never escalates to this on its own. |
| *(none)* | `resume` if state exists, otherwise ask for the idea — this is the one legal question outside a gate. |

## Rules that bind every phase

1. **Gate questions carry UX choices** — [rules/questions.md](rules/questions.md)
2. **Files stay small** — [rules/modularity.md](rules/modularity.md)
3. **Never block between gates** — [rules/autonomy.md](rules/autonomy.md)
4. **Tests first** — [rules/testing.md](rules/testing.md)
5. **Agents own disjoint files** — [rules/collaboration.md](rules/collaboration.md)
6. **Assume every agent dies** — [rules/resilience.md](rules/resilience.md)

If a phase instruction and a rule conflict, the rule wins.

## Non-negotiables

- **Write state after every unit of work**, and a `start`/`end` line to
  `.pipeline/journal.jsonl`. Any phase can be killed and re-entered cold; the journal is
  what tells the next run where it stopped.
- **Silence is never success.** An agent returning nothing has died, not finished. Status
  advances on evidence — tests that ran — never on an agent's own report.
- **Every unknown becomes an assumption plus a queued question**, never a stall and never
  a silent choice. `docs/ASSUMPTIONS.md` and `.pipeline/question-backlog.json`.
- **Contracts freeze before parallel work starts, and are reviewed before anything is
  spawned against them.** No exceptions; this is what makes the fan-out safe, and an error
  here is multiplied by every module.
- **No implementation before a failing test**, including bug fixes.
- **Nothing important is decided or checked by one agent alone.** The decomposition comes
  from a panel, the contracts from two adversarial lenses, each module's tests from an
  auditor who asks what a wrong implementation could still pass, and each finished module
  from a reviewer who did not write it. Green tests are not a reviewed module
  ([parallelism.md](references/parallelism.md)).
- **Gate A carries every pre-build question.** It is not a first instalment. If it produced
  fewer than ~25 recorded decisions, it was run wrong — the build is then 25 guesses
  wearing a trench coat, and Gate B cannot rescue it.
- **Gate B questions need Phase 6 evidence.** No finding, no question. Anything that could
  have been asked at Gate A and was not gets the reversible default and an assumption
  entry, never the last gate's attention.
- **The user chooses the design system.** Phase 2 prepares options; it never decides. If
  the user supplied one, it is used as-is and no alternatives are offered.
- **Two passes, then stop.** After the final Phase 5, write `docs/PIPELINE-SUMMARY.md`
  and end. Do not start a third pass, do not re-open Gate B, do not offer to "just quickly
  add" anything. Outstanding work goes to `docs/HANDOVER.md`.
- **Report honestly.** A phase report that says "all tests pass" when a suite was skipped
  is the single most expensive thing you can do in an unattended pipeline.

## Phase report

Every phase appends to `docs/PIPELINE-LOG.md`: what ran, what was decided, what was
assumed, what is queued for the next gate, and what is now true about the repo. This log
is what the user reads instead of having watched.

**It is a log entry, not a deliverable.** Write it and move straight into the next phase.
Do not repeat it to the user, and do not treat having written it as having finished
something — see *Run to the next gate* above. The report exists precisely because nobody
is watching; producing one is not a reason to stop and check whether they are.
