# testing — local conventions

See `README.md` for what this module is. This file is implementation-facing.

## Ownership

**Main-agent only** (Rule 5), like `contracts/` and `app/`. Every module's tests depend on
this, so a module agent changing it to suit its own suite would silently change the meaning
of fifteen other suites.

A module that needs different behaviour from the fake files a contract request rather than
editing it.

## Commands

```bash
python -m pytest src/testing -q
python -m pytest src/engine -q     # the conformance suite — the real check on this module
```

## Rules specific to this module

- **Never make the fake more capable than the real engine.** A test that passes here and
  fails against Blender is worse than no test, because it manufactures confidence. If the
  fake cannot express something honestly, the check belongs in
  `engine/conformance.py`'s `BLENDER_ONLY_CHECKS`.
- **Never make it less capable than its documented limits without saying so.** The limits in
  `README.md` are load-bearing — several modules were written against them and their authors
  reasoned about them explicitly. Changing one silently invalidates that reasoning.
- **Raise the same `EngineError` rules the real engine raises**, with the same `rule`
  strings. The conformance suite asserts on those strings, and an agent recovering from a
  named rule is the whole point of the error contract.
- **Keep it deterministic.** No clock, no global RNG, no iteration over an unordered set
  where output order is observable. A flaky fake makes every suite flaky at once.

## The size overage

`fake_engine.py` sits a little over the 300-line soft cap. It was already split twice —
`mesh_helpers.py` took the stateless geometry, `fake_surfacing.py` took materials/UV/bake as
a distinct actor. What remains is mesh and modifier operations mutating the same
`FakeObject` records; splitting those apart would separate operations that share state,
which is a false seam and worse than the overage. Documented rather than mechanically
obeyed.

## Adding a capability

1. Does `EngineProtocol` declare it? If not, that is a contract change first.
2. Implement it here **honestly** — if it cannot be modelled faithfully, model the
   bookkeeping and document the limit in `README.md`.
3. Add a conformance check in `src/engine/conformance*.py` so the real engine is held to the
   same behaviour, and put it in the right registry (`UNIVERSAL`, `BLENDER_ONLY`, or
   `FAKE_ONLY`).
4. Add a test here if the fake's own logic is non-trivial.

Step 3 is the one that gets skipped and the one that matters: a capability in the fake with
no conformance check is a place the fake and Blender are free to diverge unnoticed.
