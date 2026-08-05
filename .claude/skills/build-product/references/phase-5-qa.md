# Phase 5 — QA (unattended, concurrent agents)

Two suites, many agents, run concurrently. Then triage, because an unattended agent acting
on an unverified finding will "fix" working code.

## Spawn them concurrently, not in the background

Spawn each suite as **one message with many tool calls**, every one of them
`run_in_background: false`. They run at the same time and the message returns when they are
all done, so you keep control and go straight into triage.

`run_in_background: true` would end the turn here, every time. This phase's deliverable is
the triaged report, triage needs every finder's result, and polling for them is forbidden
([Rule 6](../rules/resilience.md)) — so a backgrounded wave leaves nothing to do but
stop and wait for a user who is not there. That is not a lapse of will; it is the only move
left. Do not create the situation.

See [agent-briefs.md](agent-briefs.md#concurrency--parallel-and-background-are-not-the-same-thing).

## Suite 1 — Backend

| Agent | Hunts |
|---|---|
| `be-contract` | Every public interface in `.pipeline/modules.json` against `contracts/`. Undocumented fields, wrong nullability, drifted error shapes. |
| `be-edges` | Empty, huge, zero, negative, unicode, duplicate, concurrent. Every documented error path actually reachable. |
| `be-integration` | Real DB and real handlers. Transactions, rollback, migrations forward and back, N+1s. |
| `be-security` | Authorisation per endpoint (not just authentication), input validation, injection, secrets in code or logs, dependency advisories. |
| `be-resilience` | Dependency down, slow, or lying. Timeouts, retries, partial failure, idempotency of anything the user can double-click. |

## Suite 2 — Frontend (Puppeteer)

Structure and conventions: [puppeteer-harness.md](puppeteer-harness.md).

| Agent | Hunts |
|---|---|
| `fe-journeys` | Every journey named at the gate, end to end, as a person does it. |
| `fe-states` | Empty, loading, error, success, offline, slow network, and every state the gate specified. |
| `fe-responsive` | The gate's device list at real viewports. Overflow, touch targets, reachability. |
| `fe-a11y` | axe on every route, plus keyboard-only traversal, focus order, focus visibility, screen-reader labels. |
| `fe-design` | Rendered computed styles against `DESIGN.md` tokens. Off-token colours, spacing, radii, type. |
| `fe-hygiene` | Console errors and warnings, failed requests, unhandled rejections, layout shift, obvious leaks. |

## When a QA agent dies

The most dangerous failure in this phase, because a dead finder and a clean area look
identical — both produce no findings. [Rule 6](../rules/resilience.md):

- Every finder must return an explicit `{"findings": []}` for a clean sweep. **A missing,
  empty, or malformed return is a death**, and is retried, not recorded as "nothing found".
- Journal each finder's `start` and `end`. At triage, any `start` without an `end` is an
  area that was **not tested** — it does not get a pass by default.
- A finder that dies twice is quarantined, and its area is listed under *what was not
  tested* in the report. An untested area named honestly is worth far more than a suite
  that reports green because nobody looked.
- The suite gate is "every finder returned" plus "no unverified P0/P1" — never just the
  absence of findings.

## First, check the tests could ever have failed

Before any finding is triaged, spend one git command per module. A suite that passes proves
nothing if it would also have passed against no implementation at all, and every finding
below is interpreted through that suite.

Phase 4 commits `test(<module>)` while the module is still stubbed and throwing, then
`feat(<module>)` when it goes green ([phase-4-implementation.md](phase-4-implementation.md)).
The gate compares their order for every module:

```bash
node .pipeline/check.mjs        # includes the tests-first check
```

Do not hand-roll this with `git log --grep`. That flag takes a POSIX regex, where the
parentheses in `test(orders):` do not mean what they mean in most languages — the pattern
matches nothing and the check silently passes. The gate reads the subjects and matches them
itself for exactly that reason.

A module whose tests arrived **after** its implementation was not built test-first, whatever
the suite says now. That is a Rule 4 finding in its own right: record it in the QA report,
raise it at the gate, and treat that module's green as weaker evidence than the others'.

This is the only place the RED commit is ever read. Phase 4 creates it and calls it "the
evidence the tests were real"; without something opening git in Phase 5, that sentence
describes an artefact nobody looks at — which is the shape of every other silent failure
this pipeline works to avoid.

## Triage — the part that is not optional

Raw findings land in `.pipeline/qa/<agent>.json`. They are **not** defects yet.

1. **Dedupe.** Six agents will report one broken button six ways.
2. **Classify.** P0 breaks a gate journey. P1 breaks a documented behaviour. P2 is a quality
   or consistency defect. P3 is an improvement — those go to Phase 6 and then Gate B, not to
   a fix.
3. **Verify adversarially — P0 to P2 only.** Each gets a second, independent agent whose
   brief is to *refute* it: reproduce from a clean state, or mark it unreproducible. Default
   to refuted when uncertain. Only reproduced findings become defects.
4. **Attribute.** Map each defect to its module and owner in `modules.json`.

Classify before refuting, not after. P3 is defined here as something nothing will fix, so
spawning an adversarial agent per P3 buys a verdict that changes no decision — and on a
large sweep the P3s are the bulk of the list. Refute what could become work.

The one thing that costs is honesty about what was skipped: an unverified P3 carries to the
gate **labelled unverified**, never as an established fact. "Six agents reported it and
nobody checked" is a different claim from "reproduced from a clean state", and Gate B is
where the difference matters.

Write `docs/qa/report-<iteration>.md`: what ran, what was found, what was refuted and why,
what is deferred. **Say what you did not test.** A QA report that omits a skipped suite is
worse than no report, because the next phase trusts it.

## Fix loop

P0 and P1 are fixed in this phase, test-first ([Rule 4](../rules/testing.md)):
failing regression test named after the defect, then the fix, then both suites. P2 fixes
only if cheap and in a module already open. P3 never — it is Phase 6 material.

Re-run both suites fully after the last fix. Never assume an earlier green still holds.

## Also check here

Phase 5 is where cross-cutting rules are enforced, since Phase 4 agents each saw only
their own module:

- No file over its hard cap ([Rule 2](../rules/modularity.md))
- No cross-feature import bypassing an `index.ts`
- Every module has `README.md` and `CLAUDE.md`, and its commands actually run
- `docs/ARCHITECTURE.md` matches the directory tree that exists
- Coverage floors met; no quarantined flaky tests left unfiled

Violations are defects, filed and fixed like any other.

## Exit

```bash
node .pipeline/check.mjs
```

Exit 0 or the phase is not done ([the gate](pipeline-state.md#the-gate)). It re-runs both
suites itself, so "green" here is measured rather than remembered.

Both suites green. No unverified P0 or P1. Report written.

**Pass 1** — improvements and refuted-but-interesting findings queue into
`.pipeline/question-backlog.json` as raw material for Phase 6. `.pipeline/state.json` → `phase: 6` — the review research phase, not a gate.

**Pass 2 (`final: true`)** — there is no gate left to queue for. Everything unfixed becomes
a written known issue in `docs/HANDOVER.md` with a repro and a suggested fix. Then write
`docs/PIPELINE-SUMMARY.md`, set `.pipeline/state.json` → `"status": "finished"`, and **stop
the run** — see [phase-7-gate-b.md](phase-7-gate-b.md). Do not start another pass.

Writing `status` is what closes the run. Leave it and the state file still reads as a
pipeline in flight, so the `Stop` hook keeps arguing with an ending that was correct —
and goes on doing it to unrelated sessions in the same repo afterwards.

## Failure modes

- **Acting on unverified findings.** The most expensive failure available here.
- **Running QA agents in the foreground**, one after another. Slow, and you will cut it short.
- **Letting a QA agent fix what it found.** Finders rationalise. File it; a fresh agent fixes it.
- **Declaring green when a suite errored on startup.** Zero tests run is not zero failures.

**Do not stop here.** Write the state, then open [phase-6-review.md](phase-6-review.md) and begin it in this same turn. On pass 2 there is no Phase 6 — write the summary and end the run instead.
