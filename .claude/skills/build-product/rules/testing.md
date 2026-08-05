# Rule 4 — Tests come first

No implementation code exists before a test that fails for the right reason. This is not
a preference about quality; it is what lets unattended agents (Rule 3) know whether they
succeeded without a human looking.

## The loop

**RED** — Write the test from the module's *contract*, not from an implementation you
have already imagined. Run it. It must fail, and the failure message must be the one you
expect. A test that fails with `ReferenceError` has not been verified — stub the module
until it fails on the assertion.

**GREEN** — Write the least code that passes. Do not add cases the tests do not demand.

**REFACTOR** — Clean up under a green suite, including splitting to satisfy
[Rule 2](modularity.md). Tests do not change during refactor. If they must, you were
testing the implementation, not the contract.

Commit at each transition, **scoped to the module**: `test(orders): …` then `feat(orders): …`
then `refactor(orders): …`. The scope is not decoration — it is how the gate tells your
module's commits from the next module's, and an unscoped `test:` matches every module at
once. This agrees with [Rule 5](collaboration.md), which asks for the same shape. The RED commit is
the proof the test was real.

## What to test

Test the **public interface** of a module — what `index.ts` exports. Private files are
covered transitively. If a private file needs its own test to feel safe, its logic wants
to be a module of its own.

| Level | Covers | Speed | Network / DB |
|---|---|---|---|
| Unit | one module's decisions, edge cases, errors | ms | never |
| Contract | request/response and event shapes match the shared schema | ms | never |
| Integration | real DB, real HTTP handler, real wiring | sub-second | yes, ephemeral |
| E2E (Puppeteer) | a journey a real person takes, in a real browser | seconds | yes, seeded |

Unit tests that touch the network are integration tests that lie about their cost.

## The two suites

Every project built by this pipeline ships exactly two runnable suites:

```
npm run test:backend     # unit + contract + integration
npm run test:frontend    # Puppeteer E2E, a11y, responsive, visual
```

Each package additionally scopes its own commands in its local `CLAUDE.md`, so an agent
working in a subdirectory runs only what it affects. The full details of the frontend
harness are in
[puppeteer-harness.md](../references/puppeteer-harness.md).

## Determinism

Flaky tests are worse than missing tests, because an unattended agent will "fix" a
passing feature to chase them.

- Fixed seed for any randomness; inject a clock, never call `Date.now()` in a tested path
- No sleeps — wait for a condition, with a timeout
- Ephemeral database per run, torn down after; never a shared dev database
- Network stubbed at one boundary, declared in `docs/TESTING.md`
- A test that fails twice in ten runs is quarantined and filed as a defect, not retried

## Bugs

A defect found in Phase 5 QA is fixed the same way: **failing regression test first**,
then the fix. The regression test stays forever and is named after the defect
(`orders.cancel-after-refund.test.ts`). No fix lands without one.

## Floors

- New code: 80% line coverage in the module, 100% of documented error paths
- Every public interface in `.pipeline/modules.json` has at least one contract test
- Every user journey named at a gate has one E2E test
- Coverage is a floor to catch untested modules, not a target to farm. Do not write
  tests against getters to raise a number.
