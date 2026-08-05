# orchestration

The phase machine, the single write lock, conflict flagging, the check-cadence policy,
and assembly of the standard action report (ADR-007, ADR-005). Phase gating **is** the
concurrency-control mechanism, not a separate thing layered on top of one: a live 3D
scene is shared mutable state, structurally the case where parallel LLM writers are
measured to make conflicting implicit decisions and corrupt each other's work. Many
sub-agents read and propose in parallel; exactly one writes.

## Public interface

Everything importable from `orchestration` is declared in `orchestration/__init__.py`.
One class, `Orchestrator`, assembled from five responsibility mixins:

```python
class Orchestrator:
    def __init__(self, scene: ScenePort, *, cadence: CheckCadence = CheckCadence.EVERY_GEOMETRY_CHANGE)

    # phases
    @property
    def phase(self) -> Phase
    def can_promote(self) -> tuple[bool, tuple[AcceptanceResult, ...]]
    def promote(self, *, force: bool = False) -> Phase
    def tools_for(self, role: ToolRole) -> tuple[ToolSpec, ...]

    # write lock — implements contracts.WriteLockManager
    def acquire(self, holder: str, phase: Phase, *, ttl_ops: int = 64) -> WriteLease
    def release(self, lease: WriteLease) -> None
    def current(self) -> WriteLease | None
    def verify(self, lease: WriteLease) -> None

    # proposals and conflicts
    def propose(self, p: Proposal) -> str          # no lease parameter — see Invariants
    def pending(self) -> tuple[Proposal, ...]
    def find_conflicts(self) -> tuple[Conflict, ...]
    def accept(self, proposal_id: str, lease: WriteLease) -> ActionReport

    # the action loop
    def perform(self, op: Operation, lease: WriteLease) -> ActionReport
    def set_cadence(self, c: CheckCadence) -> None
    def add_operator_note(self, text: str) -> None

    # run control
    def pause(self) -> None
    def resume(self) -> None
    @property
    def state(self) -> RunState
```

Plus two locally-defined exceptions (see "Contract gaps" below): `ProposalConflict` and
`RunPaused`. And `ScenePort` — a typed `Protocol` describing the slice of the future
`src/scene` module's interface this module depends on.

## Layout

One file per responsibility, mirroring `src/measure/`'s and `src/detail/`'s split:

| File | Owns |
|---|---|
| `phases.py` | phase machine, promotion, tool-role partitioning |
| `locking.py` | the single write lock (`contracts.WriteLockManager`) |
| `proposals.py` | propose / pending / conflict flagging / accept, plus `ProposalConflict` |
| `reporting.py` | perform, check cadence, action-report assembly |
| `run.py` | pause / resume / run state, plus `RunPaused` |
| `scene_port.py` | `ScenePort` — the typed slice of `scene`'s future interface |
| `conftest.py` | test-only — `FakeScene` and the `scene` fixture, not part of the public interface |

## Invariants

- **Phase gating is the concurrency mechanism.** There is no separate "lock manager"
  concept; `Orchestrator` *is* both the phase machine and the `WriteLockManager`
  implementation, because ADR-007 says phase splitting has near-zero collision risk *by
  construction* and reuses the same staged structure the product's phases already have.
- **`propose` takes no `WriteLease`.** This is not an oversight — it is the entire
  mechanism that lets any number of `INSPECT`-role agents call it while a writer holds
  the lock. No implementation choice can start requiring one without also breaking the
  method's own signature.
- **A stale lease is reclaimable.** `WriteLease.is_stale` compares against the scene's
  operation count (`scene.document().head`), not wall-clock time — deliberately, so a
  paused run does not burn a holder's lease and tests stay deterministic. Agents die
  mid-operation (Rule 6); without expiry, one dead holder wedges the run forever.
- **A conflict is never auto-resolved.** `accept` on a proposal that is party to any
  `Conflict` in `find_conflicts()` must raise `ProposalConflict`, never silently apply
  one side. Figma-style last-writer-wins was explicitly rejected for geometry (ADR-007):
  a silent overwrite produces an invalid model, not just a surprise.
- **A forced promotion is recorded, not silent.** `promote(force=True)` overriding a
  failing `can_promote()` must leave a trace an operator can find later — Gate A 6.3's
  "the user chose report-over-block" is only honoured if the override stays visible.
  This module's working convention (not yet frozen in `src/contracts/`): route the
  transition through `scene.apply(Operation(kind="phase_promotion", params={"forced":
  True, ...}))`, reusing the log `scene` already keeps rather than inventing a second
  audit channel. See "Contract gaps".
- **`tools_for` bounds are load-bearing.** Between 1 and 8 tools per role, always;
  `INSPECT` gets only `mutating=False` tools. The upper bound reflects published
  accuracy-optimal visible-tool-set research (`contracts.ToolRole`'s own docstring), not
  a style preference — a role handed thirty overlapping tools measurably invents tool
  names and borrows the wrong argument schema.
- **A skipped check never reads as clean.** `ActionReport.checks_skipped=True` is
  enforced honestly by `perform`; `ActionReport.render()` already refuses to let that
  read as a clean result (that check lives in `contracts`, not here).
- **An operator note is delivered exactly once.** MCP is call/response; the next tool
  response is the only path a mid-run redirect has into a connected agent's context.
  `perform` drains and clears the note queue on every call, whether or not there was a
  note to deliver.
- **Pause is cooperative and checked before, not during, an operation.** `perform`
  checks `self.state` before calling `scene.apply`, and raises `RunPaused` rather than
  starting a new operation — never aborts one already in flight. This module chose
  *raise* over *defer* for the paused-`perform` case: a caller that ignores a raised
  error is unambiguously a bug, where a deferred call could be silently lost once MCP's
  call/response cycle for that turn ends.

## Contract gaps

Flagged in this task's `contractRequests` output rather than resolved here (Rule 5 —
`src/contracts/` is main-agent only):

1. **`scene`'s real interface is unbuilt.** `ScenePort` in `scene_port.py` is this
   module's own working assumption (`apply`, `document`, `undo`, `subscribe`), not a
   frozen contract. `src/scene` is listed `"planned"` in `.pipeline/modules.json`.
2. **No contract type exists for "a promotion was forced."** This module's stub
   documents a convention — a `phase_promotion` pseudo-`Operation` carrying
   `params={"forced": ...}` — rather than a dedicated audit type. A `PromotionRecord` in
   `src/contracts/phases.py` alongside `WriteLease`/`Conflict` might be cleaner.
3. **`tools_for`'s registry source is unspecified.** The constructor takes only `scene`
   and `cadence` — no tool registry. `ARCHITECTURE.md` says registry *policy* lives in
   `mcp` and registry *content* lives beside each operation; where `Orchestrator` sources
   the table it filters by role and phase is an open implementation decision.
4. **No shared exception type for "run paused" or "proposal conflict."** This module
   defines `RunPaused` (`run.py`) and `ProposalConflict` (`proposals.py`) locally, shaped
   like `contracts.EngineError`/`ConstraintError`/`ToolError` (`rule`/`detail`/
   `suggestion` where applicable). Consumers wanting to catch either by a shared base
   class may want them promoted to `src/contracts/`.

## Dependencies

`contracts` only, at import time (`.pipeline/modules.json` also lists `scene` and
`measure` as design-time dependencies — this module does not import either; it depends
on their *future* interfaces only through `ScenePort` and through what `reporting.perform`
documents it will call once implemented, exactly as `src/detail/` does not import the
still-stubbed `src/measure/`, per that module's own README).

## Testing

`pytest src/orchestration` from the repo root. Every test takes the shared `engine`
fixture only if it needs one (none currently do) and the local `scene` fixture from this
directory's own `conftest.py` — a `FakeScene` backed by a real `contracts.SceneDocument`,
never a mock that only records calls. See `CLAUDE.md` for exact commands and status.
