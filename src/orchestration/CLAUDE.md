# orchestration — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever writes the bodies of the stubs here.

## Status

Currently **RED by design**. Every method on every mixin in `phases.py`, `locking.py`,
`proposals.py`, `reporting.py` and `run.py` raises
`NotImplementedError("orchestration.<name>: not implemented")`. `Orchestrator.__init__`
is real (it only stores its two constructor arguments) and `ScenePort`,
`ProposalConflict` and `RunPaused` are real, constructed types, not stubs.

25 tests across five `*_test.py` files. 24 are written against the eventual real
behaviour and fail with `NotImplementedError` right now — that is expected and correct
for this phase (Rule 4: a test that fails on the explicit stub error, never on
`ImportError`/`AttributeError`, has verified the module's shape before any logic exists).
One test is already green:
`locking_test.py::test_orchestrator_structurally_satisfies_write_lock_manager` — a
`@runtime_checkable` Protocol's `isinstance` check only asks whether the four methods
exist, not whether they work, so it passes today and would only regress if a method were
renamed or dropped. A change that makes the red/green split anything other than 24/1
needs an explanation in the commit message.

The tests were written against this module's brief, `src/contracts/phases.py` and
`src/contracts/operations.py`, and `docs/adr/ADR-007-single-writer-phase-split.md` /
`ADR-005-verification-split.md` before any implementation existed (Rule 4) — they are the
spec. Do not change a test to make it pass; if a test seems wrong, re-read the docstring
on the stub method it targets first, then the ADR it cites.

## Commands

```bash
# this module only
pytest src/orchestration -q

# one file
pytest src/orchestration/locking_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker anywhere in this module — everything here runs against a local
`FakeScene` (this directory's own `conftest.py`) with no Blender and no real `src/scene/`
installed, and must stay that way.

## Boundaries

- Write only inside `src/orchestration/**`. `src/contracts/`, `src/testing/`, and the
  root `conftest.py` are frozen surfaces owned elsewhere (Rule 5) — read them, never
  edit them.
- Do not import `src/scene/` or `src/measure/` — both are themselves still throwing
  stubs, and importing either would make this module's tests depend on behaviour that
  does not exist yet. Depend on `ScenePort` (this module's own typed assumption about
  `scene`'s shape) and on `contracts.AcceptanceResult`/`MeasurementReport` (the *shapes*
  `measure` will eventually produce), never on the real packages.
- If the contract in `src/contracts/` is missing something this module needs — see
  "Contract gaps" in `README.md` — do not edit `src/contracts/`. The gaps are already
  filed in this task's `contractRequests` output; adapt locally against the current
  contract (that is what `ScenePort`, `ProposalConflict` and `RunPaused` already are).
- `orchestration/__init__.py` is a barrel plus the `Orchestrator` class itself — it is
  allowed to *assemble* `Orchestrator` from the five mixins (that is composition, not
  logic), but no mixin method's body may move into it. If it grows any decision logic,
  that logic belongs in one of the five responsibility files instead.
- Nothing outside `orchestration/` may import `orchestration.phases`,
  `orchestration.locking`, etc. directly — only `from orchestration import <name>`, per
  `orchestration/__init__.py`'s `__all__`. Files inside this package (its own
  `*_test.py` files) may import a submodule directly when the barrel does not re-export
  something test-only (e.g. `orchestration.doubles`-style access) — see
  `src/contracts/contracts_test.py::` importing `contracts.wire` directly for the
  established precedent.

## Implementation notes for whoever picks this up

- **The write lock lives in exactly one field: `scene.document().active_lease`.**
  `contracts.SceneDocument.require_lease` already implements the live-lease comparison
  and raises `contracts.LockContention` with the right shape — `verify` should delegate
  to it, not re-derive the check.
- **Lease expiry is measured in operation count, not wall-clock time.**
  `WriteLease.is_stale(current_op)` is compared against `scene.document().head`. This is
  why `locking_test.py`'s stale-lease test advances the clock by calling `scene.apply`
  directly rather than sleeping.
- **`propose`/`pending`/`find_conflicts` need their own pending-proposal store** — there
  is nowhere in `contracts.SceneDocument` for unaccepted proposals to live, since they
  are explicitly *not* operations yet (`Proposal.to_operation` is the conversion, run
  only by `accept`). This module owns that list.
- **`promote(force=True)`'s audit trail is a documented convention, not yet a frozen
  type.** See `phases.py::promote`'s docstring for the exact `Operation` shape
  (`kind="phase_promotion"`, `params={"forced": ..., "from": ..., "to": ..., "failing":
  ...}`) that `phases_test.py::test_promote_with_force_overrides_a_failing_check_and_records_it`
  checks for. Keep the two in sync if either changes.
- **`perform`'s five steps are ordered on purpose** (verify lease → check pause → apply
  → cadence → drain operator notes) — see `reporting.py::perform`'s docstring. Do not
  reorder without re-reading `run_test.py::test_perform_while_paused_raises_and_applies_nothing`,
  which depends on the pause check running before `scene.apply`.
- **`tools_for`'s registry is not sourced by this module's constructor.** Whoever
  implements it needs to decide where the `dict[ToolRole, tuple[ToolSpec, ...]]` (or
  equivalent) comes from — see "Contract gaps" item 3 in `README.md` before inventing
  one from scratch.
- Keep the one-file-per-responsibility split from `README.md`. A mixin that grows past
  the 300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module
  under `orchestration/`, not a bigger file.

## Test layout

Mirrors the five responsibility files: `locking_test.py`, `proposals_test.py`,
`phases_test.py`, `reporting_test.py`, `run_test.py`. A new case for an existing method
gets added to the matching file, not a new top-level test file, unless it grows enough to
need its own responsibility split (split the source file the same way first).
`conftest.py` holds the one shared fixture (`scene` → `FakeScene`) every file uses; add a
new shared fixture there only if more than one test file will need it — a fixture used by
exactly one file belongs at the top of that file instead.

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/contracts/contracts_test.py`, `src/raw/raw_test.py` and
`src/spatial/spatial_test.py`: dataclasses over dicts, `from __future__ import
annotations`, and a docstring on every test stating the product-level consequence of the
test failing — not just what it checks.
