# contracts — local conventions

See `README.md` for what lives here. This file is implementation-facing.

## Ownership

**Main-agent only** (Rule 5). Sixteen modules compile against these types; an error here is
multiplied by all of them and paid back as rework, which is where an unattended build
actually loses its time.

A module that needs a change files it in `.pipeline/contract-requests.json` and adapts
locally against the current contract. That is not bureaucracy — it is what keeps a change
from landing in the middle of fifteen in-flight builds.

## Commands

```bash
python -m pytest src/contracts -q
```

## Rules specific to this file

- **Shapes and protocols only. No logic.** The one exception is validation in
  `__post_init__`, which exists to make an impossible state impossible rather than to
  compute anything.
- **`__init__.py` is a barrel** — re-exports only, no logic, and every public name listed in
  `__all__`.
- **Never import a sibling module.** `contracts` sits below everything; a dependency here
  would invert the whole graph.
- **Import order inside the package is acyclic** and must stay so:
  `geometry → engine → measurement → constraints → export_profiles → operations → phases →
  scene_doc → wire`.
- **A validation without a regression test is not finished.** Every `__post_init__` check
  here corresponds to a test in `contracts_test.py` named after the failure it prevents. If
  you add a guard, add the test that shows what it stops — otherwise a later reader will
  read it as pedantry and remove it.

## Tolerances

Three types carry a tolerance — `JoineryIntent`, `Constraint`, `AcceptanceQuery` — and they
governed the same geometry with different defaults, so one reading could be simultaneously
"not a defect" and "acceptance-failing". `reconcile_tolerance()` exists for that: an
acceptance check must be at least as loose as the rule it verifies. A check tighter than its
own rule fails geometry the rule permits.

`EPSILON` has a stated validity radius. Beyond ~100 m from the origin, float32 precision on
the wire approaches the tolerance itself, so use `epsilon_at(distance)` for anything
comparing world coordinates across a large level — the target scale is a full game district.

## Adding a type

Ask first whether it belongs here at all. It does if **more than one module needs to name
it**. If exactly one module needs it, it belongs in that module, where it can change without
a reconciliation round.
