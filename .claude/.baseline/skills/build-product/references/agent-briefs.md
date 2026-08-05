# Agent briefs

Every spawned agent gets a brief with the same seven parts. A missing part is how agents
drift, edit files they do not own, or return prose when the pipeline expected data.

```
ROLE       One sentence. What this agent is, not what it should think about.
INPUT      Exact files to read. Paths, not "the relevant docs".
BOUNDARY   Paths it may WRITE. Everything else is read-only. State it as a glob.
TASK       What to produce, concretely.
CONSTRAINTS  The rules that bind it, by path.
OUTPUT     The exact shape expected back. Schema if structured.
AUTONOMY   Rule 3, restated: never ask, never block, log and continue.
```

## Read-only vs writing

Read-only agents (research, QA finders, the product critic, and every verifier in
[parallelism.md](parallelism.md)) use `Explore` or `general-purpose` and their BOUNDARY is
`none — read only`. They return findings; the main agent decides. This keeps context cheap,
stops a finder from rationalising a fix, and — because they cannot collide with anything —
lets them run beside any amount of other work.

Writing agents (test-writers, implementers, fixers) get exactly one module's path glob
from `.pipeline/modules.json` and nothing else.

## The verifier's brief has one extra requirement

A verifier is spawned because some failure is silent. If its own output is ambiguous, it has
reproduced the problem it was sent to solve. So every verifier's OUTPUT states the clean
case explicitly:

```
OUTPUT     JSON: {"findings": [...]}  — return {"findings": []} for a clean pass.
           Never return prose, never return nothing.
```

`{"findings": []}` is a verdict. Nothing at all is a death
([Rule 6](../rules/resilience.md)), and the two must never look alike.

Give a verifier a **question it can answer wrongly**, not an invitation to approve. "Would a
plausible wrong implementation still pass these tests? Name one" produces a missing test.
"Are these tests good?" produces the word yes.

## Structured output

Any agent whose result feeds a machine step — QA findings, research question lists,
contract requests — returns JSON against a stated schema, not prose. Prose from six QA
agents cannot be deduped.

## Example — implementer

```
ROLE       You implement the `orders` module and nothing else.
INPUT      .pipeline/modules.json (entry: orders) · contracts/orders.ts ·
           src/features/orders/*.test.ts · docs/decisions/gate-A.md ·
           docs/ASSUMPTIONS.md (entries tagged orders)
BOUNDARY   WRITE: src/features/orders/**  — read anything, write nothing else.
           Need a contract change? Append to .pipeline/contract-requests.json and
           adapt locally. Do not edit contracts/.
TASK       Make every test in your path pass. Add no behaviour the tests do not demand.
CONSTRAINTS  .claude/rules/modularity.md (hard cap 200 lines, one primary export,
           index.ts is a barrel only) · .claude/rules/testing.md (do not modify tests
           to make them pass — if a test is wrong, report it, do not edit it)
OUTPUT     JSON: { "status": "green"|"blocked", "files": [...], "assumptions": [...],
           "contractRequests": [...], "testsSuspect": [...] }
AUTONOMY   Nobody is available. Unknown → take the reversible option, add it to
           `assumptions`, continue. Never ask a question. Never stop for approval.
```

## Example — test auditor

The stage between RED and GREEN. Note that TASK asks for something falsifiable: the third
question cannot be answered with reassurance.

```
ROLE       You audit the tests for the `orders` module. You write nothing and you do
           not read its implementation — it does not exist yet.
INPUT      contracts/orders.ts · src/features/orders/*.test.ts ·
           docs/decisions/gate-A.md (entries tagged orders)
BOUNDARY   none — read only.
TASK       Answer three questions from the contract and the tests alone:
           1. Which declared methods and documented error paths have no test?
           2. Which tests assert on how it is built rather than what it promises?
           3. Describe one plausible wrong implementation that would still pass.
CONSTRAINTS  Do not propose implementations. Do not judge style. A missing test is a
           finding; a test you would have written differently is not.
OUTPUT     JSON: {"findings": [{ "kind": "uncovered"|"implementation-coupled"|"passes-wrong",
           "detail": "...", "suggestedTest": "..." }]}
           Return {"findings": []} if the suite genuinely covers the contract.
AUTONOMY   Never ask. If the contract is ambiguous, that is a finding, not a blocker.
```

## Example — contract adversary

One of the two reviewers at the 4.2 barrier. Its whole value is that it is looking for
trouble rather than confirming a design.

```
ROLE       You attack the frozen contracts before nine modules are built against them.
INPUT      contracts/** · docs/decisions/gate-A.md · docs/ARCHITECTURE.md
BOUNDARY   none — read only.
TASK       Find, with a concrete example each: states these types allow that must never
           exist; fields whose nullability is wrong; operations whose failure has no
           declared error shape; and what breaks when a collection is empty, enormous,
           or delivered twice.
CONSTRAINTS  Every finding names the type and the sequence that reaches the bad state.
           No stylistic preferences. No suggestions that are merely nicer.
OUTPUT     JSON: {"findings": [{ "type": "...", "problem": "...", "reachedBy": "...",
           "fix": "..." }]}  — {"findings": []} if you cannot break it.
AUTONOMY   Never ask. Report, do not edit; contracts/ belongs to the main agent.
```

## Example — QA finder

```
ROLE       You are fe-a11y. You find accessibility defects. You never fix them.
INPUT      docs/decisions/gate-A.md (quality bar wave) · docs/TESTING.md ·
           tests/frontend/** · the running app at $BASE_URL
BOUNDARY   WRITE: .pipeline/qa/fe-a11y.json only.
TASK       axe every route; keyboard-only traverse every gate journey; check focus
           order, focus visibility, labels, and contrast against DESIGN.md tokens.
CONSTRAINTS  Report only what you reproduced from a clean state. One finding per defect.
           No speculation — if you did not observe it, do not file it.
OUTPUT     JSON array: { id, severity: P0..P3, route, journey, whatHappened,
           whatShouldHappen, reproSteps[], evidence: "path/to/screenshot.png" }
AUTONOMY   Never ask. If a route will not load, file that as the finding and continue.
```

## Concurrency — parallel and background are not the same thing

This distinction is the single most important thing on this page, because getting it wrong
ends the turn every time and no amount of "do not stop" prose can recover it.

- **Parallelism comes from one message with many tool calls.** That is what makes a wave
  run at once.
- **Backgrounding comes from `run_in_background`, and it hands control back to the user.**

So:

> **Every wave in this pipeline spawns with `run_in_background: false`.**

`run_in_background` defaults to **true**, so this must be passed explicitly — omitting it
is choosing to end the turn. Several synchronous agents in a single message still run
concurrently; the message simply does not return until they are done. You get the
parallelism and you keep control.

The rule for deciding is short: **background work you do not need in order to continue.**
This pipeline has none. Every wave feeds the step immediately after it — the RED wave feeds
the GREEN wave, the finders feed triage, triage feeds the report. Backgrounding any of them
leaves you with nothing to do but stop, which is precisely the failure.

- Cap writing agents at 4–6 concurrent. More produces integration queues, not speed.
- A long wave makes for a long turn. That is the intended shape; see
  [rules/autonomy.md](../rules/autonomy.md).
- Give every wave a wall-clock budget so a hung agent cannot stall the phase forever
  ([Rule 6](../rules/resilience.md)). Past the budget, treat it as dead and retry.
- Never fabricate a pending agent's result. If asked before it lands, say it is running.

## Liveness — every brief carries it

Agents die ([Rule 6](../rules/resilience.md)). The brief is where that is made
survivable, because a dead agent and a successful one both return nothing useful.

- **Always require an explicit result shape**, including for the empty case. A finder
  returns `{"findings": []}`; it never returns nothing. This is what makes silence
  distinguishable from success.
- Add to OUTPUT: *"If you cannot complete this, return `{"status":"blocked","reason":...}`
  rather than stopping."* A reported block is recoverable; a vanished agent is not.
- Write the `start` line to `.pipeline/journal.jsonl` **before** spawning, and the `end`
  line from the parent when the result arrives — never from inside the agent, which is
  precisely the thing that may not survive.
- The parent validates every return against the schema before using it. A malformed return
  is a death, and goes to the retry path.
- Long units get a wall-clock budget. Past it with no result, treat the agent as dead.
