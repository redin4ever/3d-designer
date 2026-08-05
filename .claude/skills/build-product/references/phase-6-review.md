# Phase 6 — Review research (unattended)

Phase 1 researched an idea. Phase 6 researches **the thing that now exists**.

Same shape as [Phase 1](phase-1-research.md): parallel read-only agents, a synthesised
summary, and — the real deliverable — **the question list for Gate B**. Research that ends
in findings has half-failed; research that ends in "here is what only the user can decide
now" has succeeded.

Nobody is watching. [Rule 3](../rules/autonomy.md) applies throughout.

## Why this phase exists

Gate A asked everything that could be asked *before* code existed. So Gate B cannot be
"what do you think now" — that would re-litigate settled decisions and waste the last
gate. Gate B may only ask what **could not have been known** at Gate A, and the only way
to find those things is to go and look at the built product.

This phase is that looking. It **checks what the product actually does**, as opposed to
what it was asked to do.

## Fan out

Spawn concurrently in one message, every one **`run_in_background: false`**. All read-only —
none writes source, none fixes anything it finds.

Same reason as every other wave: the flag defaults to **true**, and Gate B is assembled from
what these agents return, so backgrounding them ends the turn with the gate unasked
([agent-briefs.md](agent-briefs.md#concurrency--parallel-and-background-are-not-the-same-thing)).

| Agent | Question it answers | Writes |
|---|---|---|
| `behaviour` | What can a person actually do with this today? Enumerate real, working capabilities by exercising them — not by reading route tables. | `docs/research/review-<pass>/behaviour.md` |
| `drift` | Where does what was built differ from `docs/decisions/gate-A.md` and the ADRs? Every divergence, with whether it looks deliberate. | `.../drift.md` |
| `experience` | Walk each gate-named journey as a person. Where is it slow, confusing, unfinished, or surprising? Include first-run. | `.../experience.md` |
| `landscape` | Re-open `docs/research/landscape.md` and compare the built product to those competitors **now**. What is obviously missing side by side? What did we do better? | `.../landscape.md` |
| `debt` | Assumptions still open, QA P2/P3 findings, known issues, coverage gaps, files near budget, TODOs. The bill so far. | `.../debt.md` |

Each ends with a **Decisions for the user** section: every point where it found two or more
defensible answers and picked none. That section is the raw material for Gate B.

`behaviour` and `experience` must actually run the product — dev server, real clicks, the
Puppeteer harness. An agent that reads the code and infers what it does will report the
intent, which is precisely the thing this phase exists to distrust.

## Synthesise

The main agent writes `docs/research/review-<pass>/SUMMARY.md`:

- **What exists**, as a list of what a person can do — the honest version
- **Intended vs actual** — the drift table, worst first
- **Where it falls short** of the comparable products, each with a cost to close
- **What surprised us** — behaviour nobody specified, good or bad
- **The bill** — open assumptions, known issues, deferred work
- **Decisions for the user** — deduped, grouped into Gate B wave themes, each with your
  recommended default and its impact

Obeys the markdown budget. This is the file Gate B is assembled from.

## Feed the gate

Write every open decision into `.pipeline/question-backlog.json`, tagged `gate: "B"`, with
its wave, recommended default, impact, and — required here — the **evidence** that raised
it. A Gate B question with no evidence from this phase is a Gate A question arriving late,
and it does not belong.

```json
{
  "id": "R-004",
  "gate": "B",
  "wave": "drift",
  "question": "Proposals currently send instantly with no review step. Keep it that way?",
  "options": ["Keep instant (recommended)", "Add a preview step", "Make it a setting"],
  "recommended": 0,
  "impact": "high",
  "evidence": "drift.md — Gate A wave 3 implied a review step; none was built and no assumption was logged."
}
```

## The filter

Before the gate, drop every candidate question that:

- Gate A already answered, unless the built product **contradicts** that answer — in which
  case the question is "we built X instead, keep it?", not the original question again
- Could have been asked at Gate A and simply was not — that is a Gate A failure; take the
  reversible default, log it in `ASSUMPTIONS.md`, and do not spend the last gate on it
- Concerns something already scheduled to be fixed in the final pass

What survives is genuinely new information. That is the whole point of putting a research
phase where a question round used to be.

## Also update

- `docs/PIPELINE-LOG.md` — phase report
- `.pipeline/state.json` → `phase: 7`

## Guardrails

- **Observe, do not fix.** Anything found here is filed, not repaired. A finder that fixes
  its own finding stops reporting the ones it cannot fix.
- **Distinguish observed from inferred**, exactly as in Phase 1. "The form submits twice on
  double-click" is observed; "users will find this frustrating" is inferred.
- Do not re-run the QA suites here — [Phase 5](phase-5-qa.md) already did, and its report
  is an input to this phase, not a thing to redo.

**Do not stop here.** Write the state, then open [phase-7-gate-b.md](phase-7-gate-b.md) and begin it in this same turn. Gate B is where this turn ends.
