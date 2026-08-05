# Phase 7 — Gate B (the last gate), and Phase 8 — the final pass

The pipeline is **fixed length**:

```
… 4 Build → 5 QA → 6 Review research → 7 GATE B → 8 (= 4 + 5, once) → SUMMARY → stop
```

Gate B is the last time a human is reachable, and everything chosen here must fit in
**one** build-and-QA pass. Same law as Gate A ([Rule 1](../rules/questions.md)).

## What makes this gate different

Gate A asked everything answerable before the product existed. **Gate B asks only what
[Phase 6](phase-6-review.md) discovered by looking at what got built.** Every question
carries evidence from that research. No evidence, no question.

This is the rule that keeps the last gate valuable. A Gate B that re-opens Gate A's
decisions spends the user's final attention on ground already covered.

## Before opening

Phase 6 has already produced `docs/research/review-<pass>/SUMMARY.md` and a filtered,
evidence-tagged question backlog. Two things left:

1. **Size it.** Estimate what one pass actually holds, and bring that number to the gate.
   A gate that pretends everything fits produces a final pass that finishes none of it.
2. **Order by consequence**, not by how interesting the finding was.

## Open the gate

Short and honest. Lead with the constraint:

- **This is the last round of questions.** After it, one more build-and-QA pass runs
  unattended and the pipeline stops. Say this first, plainly.
- **What the product actually does** — Phase 6's honest list, not the intended one
- **Where it drifted** from what was decided at Gate A
- **Every open assumption** from `docs/ASSUMPTIONS.md`, read out. Last vote on each.
- Roughly what fits in the final pass, so choices are made against a real budget

## The waves

4–6 waves, four questions each, back to back. Each wave built from Phase 6's findings.

| # | Wave | Source | Must include |
|---|---|---|---|
| 1 | **Drift** | `drift.md` | Where the build diverged from Gate A. Each as "we built X instead of Y — keep X?" with the built behaviour as option 1, since it exists and is therefore cheapest. |
| 2 | **Assumptions** | `ASSUMPTIONS.md` | The highest-blast-radius assumptions, assumed answer as option 1. Last chance to overturn. |
| 3 | **Gaps** | `landscape.md` | What comparable products have that this does not, now that both can be seen. `multiSelect`, effort stated, with a cap on how many fit. |
| 4 | **Rough edges** | `experience.md` | Where a journey is slow, confusing or unfinished — as previews of current vs proposed. |
| 5 | **Surprises** | `behaviour.md` | Behaviour nobody specified. Keep, change, or remove. |
| 6 | **Scope the final pass** | all | Polish vs add. Which single thing must be excellent when it stops. What is accepted as a known gap. |

Wave 1 leads with experience, never metrics. Wave 3 is the only multiSelect wave — the
rest are decisions, not shopping.

Ask "what should we **stop** doing" at least once, and ask wave 6's last question honestly:
some things will not get built, and the user should choose which rather than discover it.

## Record

- `docs/decisions/gate-B.md` — every question, option, choice, verbatim note
- New ADRs; `ASSUMPTIONS.md` reconciled
- `.pipeline/backlog.json` rewritten as the **final pass scope only**, priority-ordered
- `docs/HANDOVER.md` — everything raised and not taken, with what Phase 6 learned about
  it. This is the deliverable that replaces a third iteration.

One `docs:` commit before Phase 8 starts.

**Then run the final pass, in the same turn.** The last wave being answered is the start
of Phase 8, not the end of your turn. Do not summarise the gate, do not present the plan
for approval, do not ask whether to proceed. The next thing the user sees is
`docs/PIPELINE-SUMMARY.md` when the run is over.

## Phase 8 — the final pass

Set `pass: 2`, `final: true`, `phase: 4`, and re-enter
[Phase 4](phase-4-implementation.md), then [Phase 5](phase-5-qa.md). Four differences:

- **Contracts may change.** 4.2 starts by reconciling `.pipeline/contract-requests.json`
  and any gate decision that breaks an interface — own commit, own ADR, before any module
  reopens.
- **Modules already green stay untouched** unless the backlog or a contract change names
  them. Do not rebuild what works with no one left to catch the regression.
- **Regression tests are never deleted or relaxed** to make a new feature pass. A new
  feature that breaks an old test is a design conflict — take the reversible option, keep
  the old test, record the conflict in `HANDOVER.md`.
- **Nothing is deferred.** "Queue it for the next gate" is no longer an outcome. Anything
  not fixed becomes a written known issue with a repro and a suggested fix.

## Exit — unconditional

When the final Phase 5 completes, the pipeline **stops**. No condition to check.

Write `docs/PIPELINE-SUMMARY.md`: what was built as a list of what a person can do; every
gate decision, linked; every surviving assumption and what reversing it costs; both suites'
final state including anything skipped; known issues with repros; the handover backlog;
and **what the next person should do first**.

Then report and end. Do not start another pass, do not re-open a gate, do not offer to
"just quickly add" anything. Further work is a fresh, explicitly requested run —
`/build-product iterate` exists for that and is the user's call, not yours.

## Failure modes

- **Not telling the user this is the last gate.** They hold things back for a round that
  never comes. The most damaging mistake available here.
- **Asking a question Phase 6 did not raise.** If it has no evidence, it belonged at
  Gate A; take the default and log it instead of spending the last gate on it.
- **Accepting everything at wave 3.** An unsized backlog ships six half-features instead
  of two finished ones.
- **Quietly starting a third pass** because the backlog still has items. It always will;
  that is what `HANDOVER.md` is for.
