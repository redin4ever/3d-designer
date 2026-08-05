# raw — local conventions

## Run the tests

```
python -m pytest src/raw
```

No markers, no `bpy`, no fixtures beyond the root `engine` fixture (`conftest.py` at the
repo root — do not redefine it here). Currently 13 tests, 2 green (`RAW_TOOL_SPEC` checks
— it is real, constructed data, not a stub) and 11 red with `NotImplementedError` until
`execute`/`describe_risk` are implemented. A change that makes the red count anything
other than 0 or 11 needs an explanation in the commit message.

## Ownership

`src/raw/**` only, per `.pipeline/modules.json`. This module depends on `contracts` and
nothing else in `src/` — no `scene`, no `orchestration`, no sibling operation module. Do
not import from any of them; if a future change seems to need to, that is a sign the write
lock / undo-barrier machinery is being pulled into this module by mistake (see README's
"What this module deliberately does not do").

## Conventions specific to this module

- **`__init__.py` is a barrel only.** All logic lives in `executor.py`. If this module
  ever needs to split, split along a real seam (e.g. the risk-statement text separated
  from the execution wrapper) and keep `__init__.py`'s re-export list unchanged.
- **Do not add a sandbox, an allowlist, or an AST check.** ADR-009 is a decision, not a
  gap. A pull request that narrows what `source` may contain is reverting a choice the
  user made explicitly with the risk stated, not fixing a bug. If the risk tolerance ever
  changes, that is a new ADR superseding ADR-009, decided at a gate — not a quiet change
  in this module.
- **`execute()` must never raise for a failure inside the script it runs.** Every
  exception `engine.execute` can produce — including a `SyntaxError` from malformed
  source, raised at compile time before anything executes — is caught and turned into
  `RawResult(ok=False, error_rule="raw.execution_failed", error_detail=...)`. This is
  `contracts.RawOps.execute`'s own docstring, verbatim, describing its required caller;
  this module is that caller and there is no second one.
  `execute()` itself failing (a bug in this module, as opposed to in the script it ran) is
  the one case allowed to raise normally.
- **`objects_before`/`objects_after` come from `engine.list_objects()`, not from
  bookkeeping this module keeps separately.** `created`/`removed` are a set difference
  over those two calls — never trust a script's own account of what it did.
- **`returned` filtering is by exclusion, not by an allowlist of "safe" types.** Exclude
  modules (`isinstance(v, types.ModuleType)`), callables (`callable(v)`), dunder names
  (`__builtins__` and friends, injected by `exec` itself), and any name that was already
  present in the namespace before the script ran — the injected `engine` handle and
  anything the caller pre-seeded via `namespace=`. Everything else the script newly bound
  passes through as-is.
- **Do not describe the risk more than once.** `describe_risk()` in `executor.py` is the
  one place the exposure statement is written. `RAW_TOOL_SPEC.description` and
  `README.md` reference the same facts (no sandbox, no filesystem restriction) but should
  not duplicate the exact prose — one accurate statement beats several slightly different
  ones drifting apart over time.

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/contracts/contracts_test.py` and `src/spatial/spatial_test.py`:
dataclasses over dicts, `from __future__ import annotations`, and a docstring on every
test stating the product-level consequence of the test failing — not just what it checks.
