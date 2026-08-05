# The fan-out model

How this pipeline uses many agents, and — more importantly — when it does not.

Speed and accuracy are not traded against each other here. They come from the same two
moves, applied to different things:

- **Fan out independent work.** Ten modules built at once take one module's time.
- **Verify with someone who did not do the work.** A second, independent look catches what
  the author structurally cannot see.

The second is what keeps the first honest. Fanning out without verification just produces
wrong answers faster, and rework is where unattended pipelines actually lose their time —
not in thinking, but in building nine modules against a contract that was wrong.

## An agent earns its place two ways

Do not add agents because more sounds better. Every agent costs tokens, adds a thing that
can die ([Rule 6](../rules/resilience.md)), and adds a result someone must reconcile.
Spawn one only when it does one of these:

1. **It removes a serial dependency.** Work that could have happened at the same time as
   other work but was queued behind it.
2. **It checks something whose failure is expensive and silent.** A wrong contract, a test
   that cannot fail, a module that satisfies its tests and not its purpose. These do not
   announce themselves; they surface three phases later as a rewrite.

An agent that does neither is a slower way to do it yourself.

## Read-only agents are free to run alongside anything

[Rule 5](../rules/collaboration.md) restricts *writers* to disjoint paths. A verifier
writes nothing, so it can never collide — with a writer, with another verifier, or with a
human. That is what makes verification cheap to add:

- **Writers:** cap at 4–6 concurrent. Beyond that you get an integration queue, not speed.
- **Readers:** run as many as the work has. Reviews, audits, and finders are read-only.

So the accuracy mechanisms below cost wall-clock only where they gate the next step, and
nothing at all where they run beside it.

## The ready queue replaces fixed waves

A module is **ready** when every entry in its `dependsOn` is `green`. Not "in wave 2" —
ready. After each round, recompute:

```
ready = modules where status is planned and every dependency is green
```

Take up to the writer cap from `ready`, in dependency order, leaves first. When they land,
recompute. A module whose dependency finished early starts early; it does not wait for the
rest of an arbitrary wave to catch up.

This is the single largest speed win available in Phase 4, and it costs nothing in
accuracy — the dependency graph is doing exactly the work it was written for.

## Barriers — the only three

A barrier is a point where everything must finish before anything continues. Each one costs
you the difference between the slowest and fastest agent, so it needs a reason:

| Barrier | Why it is real |
|---|---|
| Before contracts freeze | Every module compiles against them. Nothing may start until they are settled. |
| Before integration of a dependency's dependents | You cannot build against a module that does not exist yet. |
| Before a gate | The user is answering about the whole picture, not a fragment. |

Everything else should be a queue. In particular, **the RED and GREEN stages are not a
barrier between all modules** — module A's implementer needs A's tests, not everyone's.

### If the Workflow tool is available

The per-module chain maps directly onto `pipeline()`, which runs each item through every
stage independently with no barrier between stages — module A can be in review while module
B is still writing tests:

```js
await pipeline(readyModules,
  m => agent(testWriterBrief(m),  { schema: TESTS }),
  (t, m) => agent(auditBrief(m, t), { schema: AUDIT }),
  (a, m) => agent(implementBrief(m), { schema: IMPL }),
  (i, m) => agent(reviewBrief(m, i),  { schema: REVIEW }),
)
```

Workflows need the user's explicit opt-in, so this is an option, not a requirement.

**Without it**, the same shape is approximated by batching each stage across the whole
ready set: a wave of test-writers, then a wave of auditors, then a wave of implementers.
Slower than a true pipeline — a synchronous message returns only when all of its agents do
— but it keeps the ready-queue win and every accuracy check below.

## The four verification agents

These are what stop fan-out from becoming fan-out-of-mistakes. Each is read-only, and each
exists because the failure it catches is silent.

### 1. The architecture panel — before the manifest is written

The decomposition is the most expensive decision in the build: every later agent's boundary
comes from it, and a bad seam is discovered by two agents needing each other's internals,
after both are written.

Spawn **three architects independently**, each given the gate decisions and the backlog,
each asked for a decomposition with its module list, path globs, dependency graph and the
seams it chose. Do not show them each other's work — the point is independent structure.

Then judge: score each on whether paths are disjoint, whether the dependency graph is
acyclic and shallow, whether any two modules need each other's internals, and how many
modules a typical gate journey touches. Take the winner, graft anything better from the
others, and write `.pipeline/modules.json` yourself.

Three attempts and a judgement beats one attempt iterated, because the failure mode is
*structural* — an iteration of a bad decomposition is usually a better-argued bad
decomposition.

### 2. The contract review — after freeze, before fan-out

This is the highest-leverage check in the pipeline. Every module compiles against
`contracts/`, so an error there is multiplied by the number of modules and paid back as
rework.

Spawn **two independent reviewers** on the frozen contracts, each with a distinct lens:

| Lens | Asks |
|---|---|
| **Consumer** | Take three gate journeys. Can they be expressed with these types alone? What is missing, what is ambiguous, what forces a cast? |
| **Adversary** | What states are representable that must never exist? Where is nullability wrong? What error can occur that has no shape? What breaks when a list is empty, huge, or arrives twice? |

Both return `{"findings": []}` explicitly when clean, so silence stays distinguishable from
success. Reconcile before anything is spawned against the contract — this is a barrier, and
one of the few that earns it.

### 3. The test auditor — between RED and GREEN, per module

Rule 4 already separates test-writers from implementers. Nobody, though, checks that the
tests are any good, and an implementer's job is to make them pass — so a weak suite is an
instruction to write weak code.

Per module, one auditor answers, from the contract and the tests only:

- Does every declared method have a test? Every documented error path?
- Does any test assert on the implementation rather than the contract?
- Would a plausible wrong implementation still pass? Name one.

That last question is the one that matters. Its answer is a missing test, which the auditor
returns and the test-writer adds before the implementer is spawned.

### 4. The module reviewer — after GREEN, before integration

A fresh agent that has not seen the implementation being written reads the module against
its contract and the gate decisions it was given. Green tests prove the tests pass; they do
not prove the module does what the gate asked for.

Read-only, so it runs alongside the next batch of implementers and costs no wall-clock. Its
findings go back to that module's owner as a fix, or to `.pipeline/backlog.json` if they are
a decision rather than a defect.

## What must stay with the main agent

Fan-out has a boundary. These stay central because they are the reconciliation, and handing
reconciliation to a subagent is how a codebase ends up with two of everything:

- `contracts/`, `.pipeline/*.json`, root config, migrations ([Rule 5](../rules/collaboration.md))
- Judging the architecture panel and writing the manifest
- Integration, and the decision that a module is `green`
- Every gate

## Cost discipline

Say what the fan-out cost, in the phase report: agents spawned, how many died, how many
findings each verifier produced. A verification agent that has never once changed an outcome
is a line item to remove, and you will only notice if the number is written down.
