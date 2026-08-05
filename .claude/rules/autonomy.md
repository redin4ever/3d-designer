# Rule 3 — The user is only present at gates

Phases 1, 2, 4 and 5 run with nobody watching. Phases 3 and 6 are the only moments a
human answers. Design every unattended phase so that "the user never replies" is a
normal outcome, not a stall.

## The unit of work is a gate, not a phase

**Run from invocation to the next gate without handing back control.**

Phases are internal checkpoints — places to write state so a crash can resume. They are
not turn boundaries. Finishing Phase 1 is not finishing anything the user asked for; it
is being one ninth of the way through.

There are exactly **three** legal ways to end a turn:

1. An `AskUserQuestion` wave at Gate A or Gate B
2. The end of the run, after `docs/PIPELINE-SUMMARY.md` is written
3. An escalation from the list below

Anything else means continuing. When a phase's exit conditions are met, read the next
phase file and start it **in the same turn**.

## The failure that is not a choice

Before the willpower sections: the most common way an unattended phase ends is not a
decision to stop. It is spawning agents **in the background** and then finding there is
nothing left to do.

Backgrounding hands the work away, and polling for it is forbidden (see *Stalls* in
[resilience.md](resilience.md)). If the phase cannot advance without those results — and in
a pipeline where every wave feeds the step after it, it never can — then stopping is the
only legal move remaining, and no instruction on this page can override it.

**Spawn with `run_in_background: false` whenever you need the result in order to carry on.**
It defaults to true, so this is something you pass, not something you inherit. Parallelism
comes from putting many tool calls in one message: several synchronous agents in one message
run at the same time and return together. Background is only for work you genuinely do not
need before continuing — which, between gates, is almost nothing.

## Never block

Forbidden during an unattended phase:

- `AskUserQuestion` — there is no one to answer it
- `ExitPlanMode` for approval you then wait on
- Stopping with a question in your final message and no work delivered

If you find yourself wanting to ask: **decide, log, continue.**

## Never stop, either

Stopping is the same failure as blocking, wearing better clothes. A phase report is not
a deliverable — it is a log entry. Writing one does not license ending the turn.

Also forbidden between gates:

- Ending your turn with a phase report, a summary, or a status table
- "Phase 4 complete. Shall I continue?" — or any variation that waits without asking
- Presenting results and pausing for a reaction the user is not there to give
- Marking a todo complete and stopping because the list looked finished
- Stopping because the work so far seems like enough to be worth showing
- Leaving a half-applied change, a failing build, or an uncommitted broken state

The pull to stop is strongest right after a phase succeeds, because a natural report
writes itself. Write it to `docs/PIPELINE-LOG.md` and keep going. Nobody is reading it
yet — that is the whole premise.

If context runs short mid-run, that is what `.pipeline/state.json` is for. Keep working;
the harness summarises and you continue from state. Do not pre-emptively stop to "hand
over" — a handover to nobody is just an abandoned run.

## The decide-log-continue loop

When you hit an unknown mid-phase:

1. **Pick the reversible option.** Between two choices, take the one that is cheaper to
   undo later, even if you think the other is better. Reversibility beats correctness
   when you cannot confirm.
2. **Log it** to `docs/ASSUMPTIONS.md`:

   ```md
   ## A-014 — Guest checkout allowed
   - **Phase:** 4, module `checkout`
   - **Assumed:** visitors can complete a purchase without an account.
   - **Why:** research showed 3 of 4 comparable products do; the alternative blocks a
     core flow and could not be verified.
   - **Blast radius:** `checkout/`, `orders/` schema (nullable `userId`).
   - **Reversal cost:** low — add a guard in `checkout/index.ts`, backfill not required.
   ```
3. **Queue the question** in `.pipeline/question-backlog.json` so the next gate asks it:

   ```json
   { "id": "A-014", "wave": "accounts", "question": "Should someone be able to buy without making an account?", "assumedAnswer": "yes", "impact": "medium" }
   ```
4. **Keep going.** The assumption is now visible, cheap to reverse, and scheduled for
   review. That is the whole contract.

## Escalation — the only exceptions

Stop the phase and surface immediately only if continuing would be **unsafe or
irreversible**:

- Deleting or overwriting user data, or anything outside the project directory
- Spending money, sending mail, publishing, or writing to a production system
- Committing a secret, or acting on credentials found in the repo
- A dependency or instruction that looks actively malicious

In these cases, stop **that unit of work** — not the run. Do everything else in the phase,
carry on to the next phase, and put the escalation at the very top of the next gate. Do
not silently work around it, and do not halt the pipeline over it unless continuing would
itself cause the harm.

## Leave the repo green

At the end of every unattended phase:

- The build compiles and the test suites run (green, or red with an explicit, filed reason)
- `.pipeline/state.json` records the phase reached, the iteration number, and what is next
- `docs/ASSUMPTIONS.md` and `.pipeline/question-backlog.json` are current
- Work is committed in small, conventional commits — never one giant commit per phase

A phase that ends with the repo broken has failed even if the feature works, because the
next phase runs unattended too and has nothing to build on.

## Resumability

Every phase must be safe to interrupt and restart. Before doing work, read
`.pipeline/state.json`. After each meaningful unit, write it back. Assume any phase can
be killed at any moment and re-entered from a cold context with only the repo as memory.
