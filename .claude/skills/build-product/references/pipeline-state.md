# Phase 0 — Bootstrap and resume

The pipeline runs unattended for long stretches and can be killed at any moment. State on
disk is the only memory that survives. Read it first, write it constantly.

## `.pipeline/state.json`

```json
{
  "version": 1,
  "idea": "A tool for freelance designers to send and track proposals",
  "phase": 4,
  "pass": 2,
  "final": true,
  "startedAt": "2026-08-02",
  "design": { "slug": "linear.app", "source": "catalogue", "chosenBy": "user", "gate": "A" },
  "gates": { "A": "docs/decisions/gate-A.md", "B": "docs/decisions/gate-B.md" },
  "suites": { "backend": "green", "frontend": "red" },
  "next": "Phase 5 QA — final pass, then PIPELINE-SUMMARY and stop",
  "status": "running",
  "blocked": null
}
```

`phase` is the phase currently **in progress**, not the last completed one. Write it on
entry, not on exit — a crash mid-phase must resume that phase, not skip it.

`status` is `running | escalated | finished`. **Write `finished` as the last act of the
run**, after `docs/PIPELINE-SUMMARY.md`. It is what tells the `Stop` hook the pipeline is
over; without it the hook reads `phase: 8` as a run still in flight and pushes back against
a correct ending. The hook also treats the summary file itself as terminal, so forgetting
this costs nothing — but a state file that says what is true is worth more than a fallback.

`phase` runs 0–8. `pass` is 1 or 2 and never 3. `final: true` means the run ends when this pass's Phase 5
completes — no gate, no loop, no condition to check. `design.source` is
`catalogue | user-provided | authored`, and `chosenBy` is always `user` unless every
fetch failed and the gate delegated authoring back to you.

## Sibling files

| File | Owner | Holds |
|---|---|---|
| `.pipeline/modules.json` | main agent | module ownership manifest ([Rule 5](../rules/collaboration.md)) |
| `.pipeline/backlog.json` | main agent | work items: defects, features, improvements, with source and priority |
| `.pipeline/question-backlog.json` | any agent (append only) | questions deferred to the next gate |
| `.pipeline/contract-requests.json` | subagents (append only) | contract changes a module wants |
| `.pipeline/qa/` | QA agents | raw findings before triage |
| `.pipeline/journal.jsonl` | whoever spawns work | append-only `start`/`end` per unit — the crash-recovery record ([Rule 6](../rules/resilience.md)) |

All of `.pipeline/` is gitignored except `state.json`, `modules.json` and `backlog.json`,
which are committed so a human can see where the run stands.

## Bootstrap (fresh run)

1. Refuse if `.pipeline/state.json` exists — tell the user to run `resume` or `iterate`.
2. Create `.pipeline/`, `docs/`, `docs/adr/`, `docs/decisions/`, `docs/research/`,
   `docs/qa/`.
3. **Install the rules and hooks into the project.** Copy **every** file from this skill's
   own `rules/` directory into the project's `.claude/rules/`, and **every** file from this
   skill's `hooks/` into `.claude/hooks/`, wiring each into `.claude/settings.json` —
   `check-file-size.mjs` on `PostToolUse`, `pipeline-continue.mjs` on `Stop`. The shapes are
   in `settings.json.example`, which ships beside them.

   Both directories are inside the skill, next to `references/`. **This step is the moment
   the rules start applying to the project**, and it is deliberately here rather than at
   install time: files under `.claude/rules/` are read as project instructions in every
   session, and the hooks fire on every edit. Installing the skill used to do this, so a
   project where nobody had run anything still behaved as though a pipeline were in flight.
   Running the pipeline is the act that opts a repo in.

   Copy all of them, not a list from memory. This step used to name a count and a single
   hook; both went stale, and what got dropped was Rule 6 and the `Stop` hook — the rule
   about agents dying and the hook that stops a run ending mid-phase. The two things an
   unattended run needs most are exactly the two a stale list loses.

   Never overwrite a rule the project already has — a project that has edited its rules has
   decided something, and that decision outranks the default.
4. **Copy the gate in.** `cp -r <this skill>/assets/. .pipeline/` — `check.mjs` plus the
   `lib/` it imports. This is what decides a phase is finished; see [the gate](#the-gate).
5. Seed `CLAUDE.md` (if absent) with the rule table pointing at `.claude/rules/`, plus
   `docs/ASSUMPTIONS.md`, `docs/PIPELINE-LOG.md`, `.claudeignore`, `.gitignore`.
6. `git init` and a first commit if this is not already a repo. Everything after this is
   committed incrementally — the user must be able to read the build as history.
7. Write `state.json` with `phase: 1`, `pass: 1`, `final: false`, `status: "running"`.
8. Enter [Phase 1](phase-1-research.md).

## The gate

```bash
node .pipeline/check.mjs          # after Phase 4 and after Phase 5
```

Exit 0 means the run's own exit conditions hold. It reads what is on disk — module statuses,
the journal, the commit order, file sizes, the decision records — and runs both suites. It
adds no standard the skill does not already state; every check verifies a sentence from
phase-4 or phase-5's Exit section.

Exit 2 is separate from exit 1 and the difference matters: **1 is "not finished", 2 is "I
could not judge"**. A missing `modules.json`, or one listing nothing, is exit 2 — a run with
no work list has not proved anything, and reading that as completion is the failure this
whole pipeline is arranged against.

What it cannot judge: whether the product is good, whether the gate asked the right
questions, or whether a module does what was asked rather than what its tests assert. Those
belong to the module reviewer and the user. Green here means *the run did what it says it
did*, not *the product is right* — do not report it as the latter.

## Resume

Assume the previous run was killed rather than finished — that is the normal reason resume
is being called. [Rule 6](../rules/resilience.md) is the detail; this is the order.

1. Read `state.json`. If absent, this is not a pipeline repo — offer bootstrap.
2. Read the **tail of `.pipeline/journal.jsonl`**. Every `start` without a matching `end`
   is a unit that was in flight when the process died. That is your repair list.
3. Read `git status` and `git worktree list`. Uncommitted changes and orphaned worktrees
   belong to the units from step 2 — reconcile each explicitly: finish it, or revert it and
   re-run it. Never leave one half-applied and continue. Say which you did.
4. Read `docs/PIPELINE-LOG.md` tail, `docs/ASSUMPTIONS.md`, and `.pipeline/backlog.json`
   to rebuild context. Do **not** re-read all of `docs/research/`; read its `SUMMARY.md`.
5. Re-enter the recorded phase, **skipping every unit the journal shows finished**.
   Re-running a finished unit is safe under the idempotency contract but not free, and on a
   long build that waste is what kills the retry the same way it killed the first attempt.
6. Modules at `status: "failed"` from a previous run get one fresh attempt on resume. If
   they fail again, leave them failed and let the gate decide.

## Status

Print, without doing work: phase, pass, chosen design, both suite statuses, backlog
counts by type and priority, open assumption count, queued question count, and the last
three `PIPELINE-LOG.md` entries.

## Idempotency contract

Every phase must be safe to run twice. Concretely:

- Phase 1 skips research files that already exist and are newer than the idea statement
- Phase 2 skips the fetch if `DESIGN.md` is present and matches `state.design.slug`
- Phase 3 skips waves already recorded in `docs/decisions/gate-A.md`
- Phase 4 skips modules at `green` unless their contract changed
- Phase 5 re-runs suites fully — QA results are never assumed to still hold
- Phase 6 skips review files already written for this pass; the synthesis is always redone
- Phase 7 skips waves already recorded in `docs/decisions/gate-B.md`
