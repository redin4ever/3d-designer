# Contributing

## The loop

**RED → AUDIT → GREEN → REVIEW.** Every module in this repository was built that way and
the discipline is what the codebase is made of, not ceremony around it.

1. **RED** — write the tests from the module's *contract*, not from an implementation you
   have already pictured. Run them. They must fail on an assertion or a
   `NotImplementedError`, never an `ImportError`; stub the module until that holds.
2. **AUDIT** — before implementing, ask the question that matters: *what plausible wrong
   implementation would still pass these tests?* On this codebase that question found six
   real holes, including a `spatial.invalidate` that could have been a no-op and an
   `engine.reset` that could have cleared a private ledger while leaving Blender's default
   cube in the scene forever.
3. **GREEN** — write the least code that passes. Do not add behaviour the tests do not
   demand.
4. **REVIEW** — someone who did not write it reads it against the contract. Green tests
   prove the tests pass; they do not prove the module does what was asked.

**Never edit a test to make an implementation pass.** If a test looks wrong, it is usually
describing a requirement you have not read yet. Say so; do not quietly change it.

## Commits

Conventional, scoped to the module, one per RED/GREEN/REFACTOR step:

```
test(railing): posts stay plumb on a rake
feat(railing): array along arc length with forced corner positions
```

The scope is not decoration — it is how the gate tells one module's commits from another's.

## Ownership

`.pipeline/modules.json` is the authority on who may write where. An agent writes only
inside its own path glob and reads anything.

Main-agent only, because they are the reconciliation points and handing reconciliation to a
module owner is how a codebase ends up with two of everything:

- `src/contracts/` — the frozen shared surface
- `src/testing/` — every module's tests depend on it
- `src/app/` and `src/forge3d_cli.py` — the composition root, the one place allowed to know
  about every module at once
- root config, `.pipeline/*.json`

Need a contract change? Do not edit `src/contracts/`. Append to
`.pipeline/contract-requests.json` and adapt locally.

## The seam that matters most

**`src/engine/` is the only module that may `import bpy`.** Everything else speaks
`contracts.EngineProtocol`.

This is not a style preference. It is why the whole decision layer tests in a tenth of a
second without Blender, why a Blender version bump touches one module instead of fifteen —
and Blender ships breaking Python API changes with no deprecation policy — and why sixteen
modules could be built in parallel at all.

If you find yourself wanting to import `bpy` outside `src/engine/`, the operation you want
belongs on `EngineProtocol`.

## File size

300 significant lines soft, 1000 hard; tests get 1.5×. Split along a *responsibility*
seam — a distinct decision, a distinct actor, a distinct lifecycle — never at a line count.
A 900-line file cut at line 450 produces two shallow files and one new import, which is
worse than the original.

`.claude/hooks/check-file-size.mjs` reports after every write. It advises; it does not
block.

## Before you say it works

Run both suites and the doctor:

```bash
python -m pytest src -q && node --test frontend/tests/ && python src/forge3d_cli.py doctor
```

Then check the gate, which reads what is on disk rather than taking your word for it:

```bash
node .pipeline/check.mjs
```

Green there means *the run did what it says it did*. It does not mean the product is
right — that is what the review and the gates are for.

## Reporting

If a suite was skipped, say so. If something is written but unverified, say that too. On a
codebase built mostly by agents, a report that says "all tests pass" when a suite never ran
is the single most expensive thing anyone can produce — every decision after it is made on
a false premise.
