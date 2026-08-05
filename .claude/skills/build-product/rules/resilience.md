# Rule 6 — Assume every agent dies

Long unattended runs get interrupted. A subagent crashes, a context window fills, a
process is killed, a machine sleeps. None of that is exceptional — over a build of any
size it is the expected case.

[Rule 3](autonomy.md) says never stop voluntarily. This rule is about the stops you do not
choose. The pipeline must lose **one unit of work**, never the run.

## The three deaths

| Death | Looks like | Without this rule |
|---|---|---|
| **A subagent dies** | Returns null, empty, or truncated | Main agent reads "no findings" as success and marks the module done |
| **The main agent dies** | The turn simply ends mid-phase | Work half-applied; resume re-enters the phase and cannot tell what finished |
| **Something stalls** | No output, no error, no end | The run waits forever on work that will never arrive |

The dangerous one is the first, because it does not look like a failure. Silence and
success are the same shape.

## The journal

`.pipeline/journal.jsonl` — append-only, one line per work unit, written **before** the
work starts and again when it ends:

```jsonl
{"t":"start","unit":"module:orders","agent":"impl-orders","attempt":1}
{"t":"end","unit":"module:orders","status":"green","tests":"14 passed","files":6}
{"t":"start","unit":"module:billing","agent":"impl-billing","attempt":1}
```

A `start` with no matching `end` is a unit that was in flight when something died. That is
the entire recovery mechanism, and it costs one line of I/O per unit.

Never rewrite or compact the journal mid-run. Its value is that it is append-only.

## Status advances only on evidence

The rule that makes the first death survivable:

- A module becomes `green` because **its tests ran and passed**, never because the agent
  that built it said so
- An agent returning `null`, `""`, malformed JSON, or a schema-violating object has
  **failed**. Treat it exactly like an error, not like an empty result.
- "No findings" and "the finder died" must be distinguishable. Require finders to return
  an explicit `{"findings": []}` — absence of output is death, not a clean bill of health.
- Never infer completion from a missing failure

## When a unit dies

1. **Retry it**, up to twice, with the same brief. Most deaths are transient.
2. On the third failure, **quarantine it**: mark `status: "failed"` in
   `.pipeline/modules.json` with the reason, and **carry on with the other units**. One
   dead module must not take the phase with it.
3. Record it in `docs/ASSUMPTIONS.md` and queue it for the next gate.
4. If a quarantined module is a dependency of others, skip its dependents too and say so —
   do not build against a module that does not exist.

A phase that ends with two of nine modules quarantined and seven green is a **success with
known gaps**. A phase that ends with nothing because one agent died is a failure.

## Half-applied work

Death mid-write leaves a tree nobody planned. Prevent and detect:

- **Commit per unit**, not per phase. An uncommitted unit is a unit that can vanish.
- On resume, `git status` is read *before* anything else. Uncommitted changes belong to
  whatever the journal shows in flight.
- Reconcile explicitly: either finish that unit, or revert it and re-run it. **Never leave
  it and continue** — a half-written module compiles about half the time, which is worse
  than it not existing.
- Say in the phase report which you did.

## Stalls

A stall is death that has not admitted it. Give every long unit a wall-clock budget from
the moment its `start` line is written. Past the budget with no `end`, treat it as dead
and go to the retry path.

Do not poll a background agent in a sleep loop; the harness reports completion. The budget
is a backstop for the case where it never will.

## Worktrees

An agent that died in an isolated worktree leaves its work stranded there. On resume, list
worktrees and reconcile every one: merge it if the unit was complete, discard it if not,
and never leave an orphan for the next run to trip over.

## Resume

Read in this order, before doing any work:

1. `.pipeline/state.json` — the phase
2. `.pipeline/journal.jsonl` — the tail, for units in flight
3. `git status` and `git worktree list` — for what physically survived
4. `.pipeline/modules.json` — for what is green, failed, or untouched

Then re-enter the phase and **skip every unit the journal shows finished**. Re-running a
finished unit is safe by the idempotency contract, but it is not free, and on a long build
the waste compounds until the run dies again for the same reason it died the first time.
