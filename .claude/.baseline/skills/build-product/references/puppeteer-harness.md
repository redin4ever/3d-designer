# Puppeteer frontend harness

The frontend suite drives a real browser. It is the only place the product is checked as a
person experiences it, so it must be reliable enough that an unattended agent can trust it.

## Layout

```
tests/frontend/
  harness/
    browser.ts        # launch, viewport presets, teardown
    server.ts         # start app + wait for ready, ephemeral port
    seed.ts           # deterministic fixtures per test
    axe.ts            # accessibility injection + report
    visual.ts         # screenshot capture + token comparison
    selectors.ts      # data-testid helpers — no CSS-class selectors anywhere
  journeys/           # one file per gate-named journey
  states/             # empty / loading / error / offline
  responsive/         # viewport matrix
  a11y/               # per-route axe + keyboard traversal
  design/             # computed style vs DESIGN.md tokens
  CLAUDE.md           # this suite's commands and conventions
```

Every file obeys [Rule 2](../rules/modularity.md). Harness helpers exist so that a
test file reads as the journey it describes, not as browser plumbing.

## Determinism

The whole value of this suite is that red means broken. Protect that:

- **Never `waitForTimeout`.** Wait for a selector, a response, or a network-idle condition,
  with an explicit timeout.
- **Ephemeral server and database per run**, seeded from `seed.ts` with a fixed seed.
  Never point at a shared dev environment.
- **Freeze time and randomness** in the app under test via an injected clock, so visual
  comparison and any date-dependent assertion are stable.
- **Block third-party network** at the browser level. An analytics script must not be able
  to fail the suite or leak data during a test.
- **`data-testid` only.** A test that selects on a class breaks when a token changes, which
  makes the design system feel expensive.
- A test failing twice in ten runs is quarantined and filed as a defect, not retried.

## What each area asserts

| Area | Assertion |
|---|---|
| `journeys/` | A person can complete the flow the gate named, and the end state is right |
| `states/` | Each state renders what the gate specified — including the error copy |
| `responsive/` | At each gate device width: no horizontal overflow, touch targets ≥ 44px, nothing critical below the fold on first paint |
| `a11y/` | Zero axe violations at the gate's target level; every journey completable by keyboard alone; focus always visible |
| `design/` | Computed colour, spacing, radius and type resolve to `DESIGN.md` tokens — not to approximations of them |

`design/` is what stops the design system decaying. It reads computed styles from the
rendered page and compares to the token values parsed from `DESIGN.md`, so drift fails a
test instead of accumulating.

## Artefacts

Screenshots, traces and axe reports go to `.pipeline/qa/artifacts/<iteration>/` —
gitignored. Every finding cites an artefact path; a QA finding with no evidence gets
refuted at triage.

Keep the previous iteration's artefacts until the next gate closes, so a "this regressed"
claim can be checked rather than argued.

## CI and headless

Headless by default; `HEADED=1` for local debugging. Same seed, same viewport matrix, same
timeouts in CI and locally — a suite that only passes on one machine is not a suite.

If the browser cannot launch, the suite **fails loudly**. It must never skip to green: an
unattended agent reading "0 failures" from a suite that never started will ship the bug.

## Why Puppeteer here

It is the mandated driver for this pipeline. Its constraint worth knowing: Chromium-family
only. If a gate answer names Safari or Firefox as required, that is a real coverage gap —
record it in `docs/TESTING.md` and `docs/ASSUMPTIONS.md` and raise it at the next gate
rather than implying the matrix is covered.
