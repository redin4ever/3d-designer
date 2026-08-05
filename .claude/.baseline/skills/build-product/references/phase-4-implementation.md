# Phase 4 — Build (unattended)

Contracts first, then many agents building behind them, with an independent check at every
point where a mistake would be expensive and silent. Nobody is watching:
[Rule 3](../rules/autonomy.md) governs every unknown.

Reads: [Rule 2](../rules/modularity.md), [Rule 4](../rules/testing.md),
[Rule 5](../rules/collaboration.md). Those are binding; this file is the sequence.
**The fan-out model — what runs at once, what must not, and why each verifier exists — is
[parallelism.md](parallelism.md).** Read it before 4.1; this file assumes it.

## 4.1 — Architecture, decided by a panel

The decomposition is the most expensive decision in the build: every later agent's boundary
comes from it, and a bad seam only announces itself once two agents need each other's
internals — after both are written.

So do not decide it alone. Spawn **three architects independently** on the gate decisions
and `.pipeline/backlog.json`, none seeing another's answer, each returning a decomposition:
module list, path globs, dependency graph, and the seams it chose with its reasons.

Judge them on what actually predicts trouble — disjoint paths, an acyclic and shallow
dependency graph, no two modules needing each other's internals, and how many modules a
typical gate journey has to touch. Take the winner, graft what is better from the others,
and then **you** write:

- `docs/ARCHITECTURE.md` — the codebase map. Top-level directories, one line each; the
  data flow through a single request; where the seams are and why they are there. This is
  the file that makes the repo navigable at scale, so keep it current, not aspirational.
- `.pipeline/modules.json` — the ownership manifest ([Rule 5](../rules/collaboration.md)):
  every module's id, owning agent, path glob, public interface file, dependencies, status.

Decompose so that **paths never intersect** and each module is one agent's day of work.
If two modules keep needing each other's internals, they are one module — merge them
before fan-out, not after a merge conflict teaches you.

## 4.2 — Freeze contracts, then have them reviewed

Write the shared surface and stop touching it: types, schemas, event shapes, error
taxonomy, in `contracts/`. Every module compiles against this. No subagent may edit it —
a module that needs a change appends to `.pipeline/contract-requests.json` and adapts
locally; you reconcile between rounds.

Also now: scaffold the project, generate `src/styles/tokens.*` from `DESIGN.md`, wire the
two test commands, install the design lint rule ([design-md-catalog.md](design-md-catalog.md)).
Verify both suites run and report zero tests rather than erroring — a suite that cannot
start will look green to an unattended agent.

**Then, before anything is spawned against it**, two independent reviewers
([parallelism.md](parallelism.md#2-the-contract-review--after-freeze-before-fan-out)): a
*consumer* that tries to express three gate journeys using these types alone, and an
*adversary* that hunts for states which must not be representable, wrong nullability,
errors with no shape, and what breaks when a collection is empty, huge, or arrives twice.

This is a barrier and it earns one. An error here is multiplied by every module and paid
back as rework — which is where an unattended build actually loses its time, not in
thinking.

## 4.3 — Build the ready set

There are no fixed waves. A module is **ready** when every one of its dependencies is
`green`; recompute after each round and start whatever just became ready
([parallelism.md](parallelism.md#the-ready-queue-replaces-fixed-waves)). A module whose
dependency finished early starts early rather than waiting for an arbitrary wave to drain.

Every ready module runs the same four-stage chain. Each stage is spawned for the whole
ready set at once — one message, every agent `run_in_background: false`, so the round
returns into this turn
([agent-briefs.md](agent-briefs.md#concurrency--parallel-and-background-are-not-the-same-thing)).

**RED — the test-writer.** Writes tests against the module's declared public interface and
the gate decisions. No implementation. It does not read another module's internals; if it
needs to, the contract is incomplete. Then verify every test **fails for the right reason**
— an assertion, not a missing file. Stub each `index.ts` with a throwing implementation so
that holds. Commit `test(<module>): …`, set `status: "red"`.

The RED commit is the evidence the tests were real. Without it, Phase 5 cannot tell a
passing test from one that never could have failed.

**AUDIT — the test auditor.** Read-only, working from the contract and the tests alone: is
every declared method and documented error path covered, does any test assert on the
implementation rather than the contract, and *would a plausible wrong implementation still
pass?* That last answer is a missing test — the test-writer adds it before any implementer
is spawned. An implementer's job is to make the tests pass, so a weak suite is an
instruction to write weak code.

**GREEN — the implementer.** One per module, from the brief in
[agent-briefs.md](agent-briefs.md), given:

- its `paths` glob — it writes there and nowhere else
- its public interface and the contracts it compiles against
- the gate decisions and assumptions relevant to it
- the instruction to make its tests pass and stop

`isolation: "worktree"` when paths could collide with a human's uncommitted work or with
another agent; the shared tree otherwise. Never two writing agents in one worktree.

**REVIEW — the module reviewer.** A fresh agent that did not watch the module being written
reads it against its contract and its gate decisions. Green tests prove the tests pass; they
do not prove the module does what was asked for. Read-only, so it runs beside the next
round's implementers and costs no wall-clock. Findings go back to the module's owner as a
fix, or to `.pipeline/backlog.json` if they are a decision rather than a defect.

Cap **writers** at 4–6 concurrent, ordered by the dependency graph, leaves first. Readers —
auditors and reviewers — are unrestricted; they cannot collide with anything.

When a round lands: run both suites, integrate, resolve contract requests, commit per module
(`feat(<module>): …`), set `status: "green"`, recompute the ready set, and go again.

### When an agent in a round dies

Expected, not exceptional — [Rule 6](../rules/resilience.md) governs.

Write a `start` line to `.pipeline/journal.jsonl` before spawning each agent and an `end`
line when it returns. Then, for every agent in the round:

- **A `null`, empty, or schema-violating return is a death**, not an empty result. It never
  means "the module needed no work".
- **`status: "green"` requires its tests to have run and passed** — never the agent's own
  claim that it finished.
- Retry a dead module twice with the same brief. On the third failure, mark it
  `status: "failed"`, log it to `docs/ASSUMPTIONS.md`, queue it for the gate, and **carry
  on with the rest of the round**. One dead agent must not end the phase.
- Skip anything that depended on a failed module, and say so rather than building against
  a module that does not exist.
- Commit each module as it lands. An uncommitted module is one that disappears with the
  next crash.

A round ending 7-green / 2-failed is a success with known gaps, and the gaps go to the
gate. A round ending with nothing because one agent died is a failed phase.

**A verifier that dies is also a death.** An audit or a review that returned nothing has
not given that module a clean bill of health. Retry it; if it will not run, say in the
phase report that the module went unreviewed, rather than letting silence read as approval.
This is the whole point of [Rule 6](../rules/resilience.md) and it applies to the
agents that check work exactly as it applies to the agents that do it.

## 4.4 — REFACTOR and enforce

Under a green suite, and with tests unchanged:

- Split every file over its hard cap. Check with `.claude/hooks/check-file-size.mjs`.
- Delete pass-through wrappers and anything the tests never reach.
- Verify no cross-feature import bypasses an `index.ts`.
- Verify no raw colour, font size, or spacing value outside the token file.

Tests changing during refactor means they tested the implementation. Fix the tests, and
note it — that is a signal the contract was underspecified.

## 4.5 — Document

Documentation is part of the phase, not a follow-up:

- `README.md` and `CLAUDE.md` **per package** — what it is, its public interface, its
  invariants, and the test and lint commands scoped to that package. An agent starting in
  that directory should need nothing from the root.
- `docs/ARCHITECTURE.md` reconciled with what was actually built.
- `docs/TESTING.md` — how to run each suite, where the stub boundary is, how to add a test.
- `docs/CONTRIBUTING.md` — the TDD loop, the ownership manifest, the commit convention.
- Root `CLAUDE.md` — refresh the codebase map and commands blocks.
- ADRs for anything decided here that the gate did not decide.
- **Run `/codebase-guides`** at the end of the first pass, once real code exists. It derives
  `docs/guides/{UI-CHANGES,BACKEND-CHANGES,ADDING-PAGES}.md` from what was actually built
  and wires them into `CLAUDE.md`. Phase 5's QA agents and the final pass both read them,
  so deriving them here is what keeps the second pass from re-exploring the codebase.

## Exit

```bash
node .pipeline/check.mjs --phase 4
```

It reads the conditions below off disk rather than taking the phase report's word for them
([the gate](pipeline-state.md#the-gate)). Exit 0 or the phase is not done.

Both suites green. No file over a hard cap. `modules.json` all green, each one audited and
reviewed. `docs/ASSUMPTIONS.md` and `.pipeline/question-backlog.json` current. Phase report
written, including the fan-out cost: agents spawned, how many died, and what each verifier
actually found. `.pipeline/state.json` → `phase: 5`.

## Failure modes

- **Fanning out before contracts freeze, or before they are reviewed.** Merge conflicts and
  a phase that ends red. The one mistake that costs a whole iteration.
- **Implementers writing their own tests.** They will write tests their code passes.
- **Treating a green suite as a reviewed module.** Tests passing and the module doing what
  the gate asked for are different claims; only one of them is checked by running anything.
- **Skipping the audit because the tests "look thorough".** Thoroughness is what the audit
  measures. If you could tell by looking, the agent would not be there.
- **One agent per feature *area* instead of per module.** Overlapping paths, and Rule 5
  stops protecting anything.
- **Spawning more agents to go faster.** Past 4–6 writers you get an integration queue.
  Speed after that comes from the ready queue and from not rebuilding against a bad
  contract — never from more concurrency.
- **Deferring docs to "after QA".** There is no after — Phase 5 leads to a gate.

**Do not stop here.** Write the state, then open [phase-5-qa.md](phase-5-qa.md) and begin it in this same turn. QA is part of the same unattended stretch as the build.
