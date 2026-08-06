# orchestration — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Six mixins (`phases.py`, `authorization.py`, `locking.py`, `proposals.py`,
`reporting.py`, `run.py`) plus four private helpers; `pytest src/orchestration` passes
63/63, stable across repeated runs.

What changed in the Gate B pass, and what it replaced:

- **Role authority moved onto the lease** (ADR-013). `acquire(holder, phase, roles=...)`
  grants roles; the new `authorize(tool_name, roles, lease)` refuses a tool the lease does
  not hold or the phase does not permit. Before this, `dispatch` read the role from the
  request itself, so `unwrap_uvs` (POLISH) and `add_railing` (REFINE) both succeeded while
  the session had never left `blockout`. `authorize` is the method `mcp_server.dispatch`
  should call; wiring it there belongs to that module.
- **`can_promote` is a real gate** (ADR-012). It evaluates per-phase `AcceptanceQuery`
  objects against live geometry through `measure.evaluate`. It used to compute
  `passed = len(produced_this_phase) > 0`, and `measure.evaluate` had zero non-test call
  sites anywhere in the product.
- **`force` is gone.** `promote()` takes no arguments. A refusal raises `PromotionRefused`
  and every failing result carries `subject`, `actual`, `expected` and a
  `suggested_operation` that is a concrete call — with no override, that is the only thing
  an unattended agent has to work from.
- **The write path is actually locked.** Three `threading` locks in `__init__`. Eight
  threads racing `acquire` produced *three* simultaneous winners before this; see
  `concurrency_test.py`.
- **The automatic check looks at neighbours.** `_new_problems` now runs
  `measure.find_clipping` and `measure.find_visual_gaps` over pairs selected through
  `spatial`, not only the single-object `measure.inspect`. A 4 m room previously produced 39
  real clipping defects and reported none while every report claimed
  `checks_scope="changed+neighbours"`.
- **Reports summarise above `contracts.DETAIL_THRESHOLD`** and say that they did. Defects
  are never dropped; only per-object detail is.
- **`_tool_registry.py` is deleted.** `tools_for` delegates to the real registry, filtered
  by the current phase.
- **`scene_port.py` is a one-line re-export.** `ScenePort` lives in `contracts` now.

Three tests in `phases_test.py` that asserted `promote(force=True)` were retired, not
weakened: ADR-012 deleted the behaviour they described, and `PhasePromotion.allow_override`
is gone from the frozen contract too. That is the only legitimate reason to retire a test.

The tests are the spec. Do not change one to make an implementation pass; if a test seems
wrong, re-read the docstring on the method it targets, then the ADR it cites.

## Commands

```bash
# this module only
pytest src/orchestration -q

# one file
pytest src/orchestration/concurrency_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker anywhere in this module. `concurrency_test.py` drives the real
`scene.Scene` over a `testing.FakeEngine`; every other file uses this directory's own
`FakeScene`. Neither needs Blender, and that must stay true.

## Boundaries

- Write only inside `src/orchestration/**`. `src/contracts/`, `src/testing/`, and the root
  `conftest.py` are frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- **`src/scene/`, `src/measure/` and `src/spatial/` may now be imported.** The old rule here
  said not to; that was written when `scene` and `measure` were throwing stubs and importing
  either would have made this module's tests depend on behaviour that did not exist. All
  three are green, and the Gate B work depends on them: `measure.evaluate` is what makes the
  promotion gate real, `measure.find_clipping`/`find_visual_gaps` are what make the
  neighbour check real, and `spatial.SpatialIndex` is what makes it affordable.
  - `measure` and `spatial` are imported **inside functions**, not at module scope, so a
    module mid-edit by a parallel agent cannot break this module's import.
  - `mcp_server` is still off limits at module scope: `ARCHITECTURE.md`'s arrow runs
    `scene → orchestration → mcp`, and importing it here reverses it. The registry arrives
    by constructor injection; `phases.tools_for` keeps a function-local deferred import only
    as a fallback for callers that pass none.
- If the contract in `src/contracts/` is missing something this module needs, do not edit it
  — append to `.pipeline/contract-requests.json` and adapt locally. Five such requests are
  open from this pass (UV metric, scene-level query, `Defect.axis`, registry injection,
  `PromotionRefused` placement).
- `orchestration/__init__.py` is a barrel plus the `Orchestrator` class — it may *assemble*
  the mixins and initialise instance state, but no mixin method's body may move into it.
- Nothing outside `orchestration/` may import `orchestration.phases`, `orchestration.locking`
  etc. directly — only `from orchestration import <name>`, per `__init__.py`'s `__all__`.

## Implementation notes for whoever picks this up

- **The write lock lives in exactly one field: `scene.document.active_lease`,** and
  `SceneDocument.require_lease` already implements the live-lease comparison. `verify`
  delegates to it rather than re-deriving the check.
- **Lease expiry is measured in attempts plus operation count, not wall-clock time.** The
  clock has to advance even when nothing is being applied: expiry used to be measured against
  `doc.head`, which only moves when an operation is applied, which only the lease holder can
  do — so a holder that died mid-operation froze the clock at the moment it stopped and the
  run wedged permanently. A waiting agent advances the clock by waiting.
- **Three locks, deliberately not one.** `_write_mutex` (re-entrant: `accept` calls
  `perform`) guards lease transitions and the whole apply-and-check path; `_notes_mutex` and
  `_pending_mutex` are separate so a reader never queues behind a writer's `perform`. Adding
  a fourth lock is fine; making them one is not — that turns "many read, one writes" into
  "one at a time".
- **`find_conflicts` must work from one snapshot.** It reads `self.pending()` once. Reading
  `self._pending` twice let an id that arrived in between reach the union-find with no
  `parent` entry, raising a bare `KeyError` out of a read-only method — 168 of them in one
  `concurrency_test.py` run.
- **`perform`'s order is the contract** (verify lease → check pause → snapshot if opaque →
  apply → cadence → drain notes). `run_test.py::test_perform_while_paused_raises_and_applies_nothing`
  depends on the pause check running before `scene.apply`.
- **Per-phase acceptance sets must stay satisfiable.** With no override, a query that cannot
  be passed is a phase an unattended run can never leave. Adding one to
  `_phase_acceptance.py` means proving a scene exists that satisfies it — the tests in
  `phases_test.py` do exactly that for each phase.
- **Every failure needs a call, not advice.** `_suggested_fix.py` maps defect classes to real
  tool names with real parameter names, checked against `mcp_server.build_registry()`. A
  suggestion naming a tool that does not exist is worse than none: it sends the agent into
  the same retry loop while looking helpful.
- Keep the one-file-per-responsibility split. A mixin that grows past the 300-line soft cap
  (`.claude/rules/modularity.md`) wants a private helper module under `orchestration/`, not a
  bigger file — `_phase_acceptance.py`, `_suggested_fix.py`, `_neighbours.py` and
  `_summary.py` are all that split being applied.

## Test layout

Mirrors the responsibility files: `locking_test.py`, `authorization_test.py`,
`proposals_test.py`, `phases_test.py`, `reporting_test.py`, `report_detail_test.py`,
`run_test.py`, `concurrency_test.py`. A new case for an existing method goes in the matching
file. `conftest.py` holds the one shared fixture (`scene` → `FakeScene`); `concurrency_test.py`
brings its own `live` fixture because a double cannot exhibit the interaction it tests.

`concurrency_test.py` lowers `sys.setswitchinterval` for its duration. A passing run does not
prove a race is absent — nothing can — but it widens the window an unguarded
read-modify-write is caught in from "essentially never" to "reliably". Never add a `sleep` to
that file: a sleep long enough to be reliable makes the test slow, and one short enough to be
fast makes it flaky.

## Style

Follows the repository-wide conventions in the root `CLAUDE.md`: dataclasses over dicts,
`from __future__ import annotations`, and a docstring on every test stating the product-level
consequence of the test failing — not just what it checks.
