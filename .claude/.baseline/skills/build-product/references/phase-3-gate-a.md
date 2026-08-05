# Phase 3 — Gate A (the user is here)

**Every pre-build question is asked here.** Gate A is not a first instalment with a
second round to follow — it is the entire conversation that can happen before code exists.

Gate B, much later, asks only what [Phase 6](phase-6-review.md) discovers by examining the
built product. Anything you could have asked now and did not is not deferred; it becomes
an assumption someone lives with, and it will not get a second hearing. Ask it now.

Read [Rule 1](../rules/questions.md) in full before the first call. This file is the
Gate A script; that file is the law on how questions are written.

## Open the gate

One short message before the first wave — not a report, an orientation:

- The product in two sentences, as you now understand it
- The three or four things research says will decide whether it works
- How many waves are coming, so the user knows the shape of what they agreed to
- **That there is exactly one more gate after this one.** The pipeline is fixed length:
  build, QA, a review of what got built, Gate B, one final build and QA, stop. And Gate B
  can only ask about what that review turns up — so anything on your mind belongs here.
- Anything that needs escalating from Phase 1–2 (a failed fetch, a hard constraint)

Then start. Waves run back to back. No work, no summaries, no "shall I continue" between
them — the user's attention is the scarce resource, do not spend it on ceremony.

## The waves

Assemble each from `.pipeline/question-backlog.json`, in this order. Four questions per
call, so most waves are one call.

| # | Wave | Must include |
|---|---|---|
| 1 | **Who and why** | Who this is for; the job it does; what "it worked" looks like for that person; what would make them abandon it |
| 2 | **Scope** | What is in v1; what is deliberately out; the one feature that must be excellent; multiSelect over the research feature list |
| 3 | **Core journeys** | The 2–3 flows that must feel excellent, step by step, as previews. First-run experience specifically. |
| 4 | **Interaction and feedback** | Empty states; loading; failure; success; undo vs confirm; how much the product should do without being asked |
| 5 | **Visual direction** | **The user picks the design system**, from the three previewed candidates *or* anything else — say in the wave message that they can name any catalogue slug, point at their own file or URL, or describe a brand to author from. Plus density, motion, dark mode, personality of the copy. Skip the pick entirely if they already supplied a `DESIGN.md`. |
| 6 | **Content and data** | What objects exist; what a user can see, edit, delete; what is permanent; import/export |
| 7 | **Accounts and access** | Can a stranger use it; sign-in method framed by friction; sharing; roles; what happens to data on account deletion |
| 8 | **Quality bar** | Devices and browsers; accessibility target; speed budget; what to do when something is slow — wait, degrade, or fail |
| 9 | **Stack and hosting** | Framed as cost, control, deploy friction and lock-in — never as a library beauty contest |
| 10 | **Ways of working** | Repo layout; how many agents build in parallel; review flow; how much to build in the first pass |

Waves 1–8 are mandatory. 9–10 may be dropped if research found genuine hard constraints
that leave no choice — say so rather than asking a question with one real answer.

Every wave needs at least one question a non-technical person could answer confidently.
Wave 9 included: "where should this run" is a question about who can afford it and who
can turn it off, not about container runtimes.

## Follow-up waves

After wave 10, look at what the answers invalidated. Answers routinely open questions the
backlog could not have contained — a scope answer that makes wave 6's data model wrong, a
journey answer that changes what sign-in means. Run 1–3 follow-up waves on exactly those.

## When to close

Close when no remaining unknown would change more than one module's public interface —
not when the backlog is empty, when the *consequential* part of it is.

Before closing, run the exhaustiveness check, because there is no second question round
for anything on this list:

- Every wave 1–8 asked, and each contained a question a non-technical person could answer
- Every high-impact entry in `.pipeline/question-backlog.json` either asked or explicitly
  downgraded with a reason
- Every irreversible decision asked. Reversible ones may be assumed; a schema shape, a URL
  scheme, or an auth model may not.
- Nothing deferred "for Gate B" — Gate B cannot take it. If you catch yourself thinking
  *we can revisit this later*, that is the signal to ask it now.

## Record before doing anything else

1. `docs/decisions/gate-A.md` — every question, its options, what was chosen, and the
   user's verbatim notes. Notes are worth more than the selection; do not paraphrase them.
2. `docs/adr/` — one ADR per decision that constrains architecture. Number them. Later
   phases may not re-litigate an ADR, only supersede it.
3. `docs/ASSUMPTIONS.md` — reconcile. Anything the gate confirmed is deleted from the
   list; anything it contradicted becomes a work item in `.pipeline/backlog.json`.
4. `.pipeline/backlog.json` — the v1 scope as work items, priority-ordered.
5. `CLAUDE.md` — update the project summary and commands blocks.
6. `.pipeline/state.json` → `phase: 4`, `pass: 1`.

Commit this as one `docs:` commit before Phase 4 starts. The build must be reconstructable
from the decisions, not from your memory of the conversation.

**Then build, in the same turn.** The user answering the last wave is not a cue to stop
and confirm the plan — it is the starting gun. Open
[phase-4-implementation.md](phase-4-implementation.md) and go. Phases 4, 5, 6 and 7 run
without another word from you until Gate B's first wave.

Do not summarise the gate back to the user, do not present a plan for approval, and do
not ask whether to begin. They answered 30 questions; the answer is yes.

## Failure modes

- **Asking about implementation.** "Postgres or SQLite" is not a gate question. "Should
  their data survive if they clear the browser" is the same decision, asked properly.
- **Options that are not real.** If you would refuse one of the options in the build, do
  not offer it.
- **Stopping early because the user seems tired.** Under-asking transfers the entire cost
  to the final pass, where it is paid in rewrites. Finish the mandatory waves.
- **Not recording notes.** The free-text a user types next to an option is the highest
  signal in the whole pipeline and it is gone the moment context is summarised.
