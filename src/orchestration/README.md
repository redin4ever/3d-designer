# orchestration

The phase machine, the promotion gate, role authorisation, the single write lock, conflict
flagging, the check-cadence policy, and assembly of the standard action report
(ADR-007, ADR-005, ADR-012, ADR-013). Phase gating **is** the concurrency-control mechanism,
not a separate thing layered on top of one: a live 3D scene is shared mutable state,
structurally the case where parallel LLM writers are measured to make conflicting implicit
decisions and corrupt each other's work. Many sub-agents read and propose in parallel;
exactly one writes.

## Public interface

Everything importable from `orchestration` is declared in `orchestration/__init__.py`.
One class, `Orchestrator`:

```python
class Orchestrator:
    def __init__(self, scene: ScenePort, *,
                 cadence: CheckCadence = CheckCadence.EVERY_GEOMETRY_CHANGE,
                 registry: dict[ToolRole, tuple[ToolSpec, ...]] | None = None)

    # phases
    @property
    def phase(self) -> Phase
    def can_promote(self) -> tuple[bool, tuple[AcceptanceResult, ...]]
    def promote(self) -> Phase                     # no force. See ADR-012.
    def tools_for(self, role: ToolRole) -> tuple[ToolSpec, ...]   # phase-filtered

    # role authorisation (ADR-013)
    def authorize(self, tool_name: str, roles: tuple[ToolRole, ...],
                  lease: WriteLease | None = None) -> None        # raises PhaseViolation

    # write lock — implements contracts.WriteLockManager
    def acquire(self, holder: str, phase: Phase, *, ttl_ops: int = 64,
                roles: tuple[ToolRole, ...] = ()) -> WriteLease
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

Plus three locally-defined exceptions: `PromotionRefused` (a `RuleError` *and* a
`ValueError`), `ProposalConflict` and `RunPaused`. `ScenePort` is re-exported from
`contracts`, where it now lives.

## Layout

One file per responsibility:

| File | Owns |
|---|---|
| `phases.py` | phase machine, the promotion gate, phase-filtered tool visibility, `PromotionRefused` |
| `authorization.py` | may this lease call this tool, in this phase (ADR-013) |
| `locking.py` | the single write lock (`contracts.WriteLockManager`) |
| `proposals.py` | propose / pending / conflict flagging / accept, plus `ProposalConflict` |
| `reporting.py` | perform, check cadence, action-report assembly |
| `run.py` | pause / resume / run state, plus `RunPaused` |
| `_phase_acceptance.py` | what "this phase is done" means, per phase |
| `_suggested_fix.py` | how a failing query becomes a call an agent can make |
| `_neighbours.py` | which object pairs the automatic check compares |
| `_summary.py` | how much of a report is worth sending |
| `scene_port.py` | a one-line re-export of `contracts.ScenePort` |
| `conftest.py` | test-only — `FakeScene` and the `scene` fixture |

## Invariants

- **Phase gating is the concurrency mechanism.** There is no separate "lock manager"
  concept; `Orchestrator` *is* both the phase machine and the `WriteLockManager`
  implementation, because ADR-007 says phase splitting has near-zero collision risk *by
  construction* and reuses the staged structure the product's phases already have.
- **A phase advances only when its acceptance queries pass, and there is no override**
  (ADR-012). `can_promote()` evaluates real `AcceptanceQuery` objects against live geometry
  via `measure.evaluate`. `promote()` takes no arguments. The query sets live in
  `_phase_acceptance.py` and are cumulative: blockout asks for geometry that is manifold with
  applied transforms, refine adds holes/clipping/gaps, detail re-asserts refine, polish adds
  UVs and the polygon budget. **Every set must be satisfiable** — with no override, a query
  that cannot be passed is a phase an unattended run can never leave.
- **Every failing query is actionable.** `subject`, `actual`, `expected` and a
  `suggested_operation` that is a concrete call (`fill_boundary_holes(object_id='wall_n')`),
  never advice. This is the whole of ADR-012's safety margin.
- **Role authority lives on the lease, not on the call** (ADR-013). `acquire` grants roles;
  `authorize` reads them back and also checks them against the session's *current* phase, not
  the lease's — otherwise the gate would be escapable by holding a lease across a promotion.
  `INSPECT` alone may be exercised without a lease.
- **`propose` takes no `WriteLease`.** Not an oversight — it is the mechanism that lets any
  number of `INSPECT`-role agents call it while a writer holds the lock. No implementation
  choice can start requiring one without breaking the method's own signature.
- **Every mutating path is serialised; no read path is.** `_write_mutex` guards lease
  transitions and the whole of `perform`; `_notes_mutex` and `_pending_mutex` are separate so
  readers never queue behind a writer. `concurrency_test.py` is the proof, and it is where
  the two races this pass fixed were found.
- **A stale lease is reclaimable.** Expiry counts operations *and acquisition attempts*, so a
  dead holder cannot freeze the clock it is measured against. Agents die mid-operation
  (Rule 6); without this, one dead holder wedges the run forever.
- **A conflict is never auto-resolved.** `accept` on a proposal party to any `Conflict` in
  `find_conflicts()` raises `ProposalConflict`. Last-writer-wins was explicitly rejected for
  geometry (ADR-007): a silent overwrite produces an invalid model, not just a surprise.
- **`tools_for` narrows; it never invents.** It returns what the real registry published for
  that role, filtered to the current phase — so "what can I do now" and "what will actually be
  accepted" are the same answer (ADR-013). The bound on how many tools a role sees at all is
  registry policy and belongs to `mcp_server`.
- **A skipped check never reads as clean**, and neither does a summarised report.
  `checks_skipped` and `detail_omitted` are both set honestly by `perform`; a summarised
  report that did not say so would read as a complete one. **No defect is ever dropped to
  save tokens** — only per-object detail is.
- **The automatic check compares neighbours, not just the changed object.** `measure.inspect`
  is single-object by construction; clipping and visual gaps are pairwise and are run over
  pairs selected through `spatial`'s maintained BVH. `op.joinery` is passed through, because a
  socketed post and two overlapping posts are identical BVH overlaps and the difference is
  declared intent, never inferred.
- **An operator note is delivered exactly once.** MCP is call/response; the next tool response
  is the only path a mid-run redirect has into a connected agent's context.
- **Pause is cooperative and checked before, not during, an operation.** `perform` checks
  `self.state` before `scene.apply` and raises `RunPaused` — this module chose *raise* over
  *defer*, because a deferred call can be silently lost once the call/response cycle ends.

## Contract gaps

Filed in `.pipeline/contract-requests.json` rather than resolved here (Rule 5 —
`src/contracts/` is main-agent only):

1. **No way to express "this object has no UVs" as an `AcceptanceQuery`.** No `MetricKind`
   and no `DefectClass` covers it, so `_phase_acceptance.py` evaluates the polish UV check
   locally and returns the same `AcceptanceResult` shape.
2. **No way to express a scene-level check.** "The scene contains at least one object" has no
   subject, and `AcceptanceQuery` requires one. Also evaluated locally.
3. **`Defect` carries the clipping insertion axis only inside its free-text `detail`.**
   `_suggested_fix.py` regexes it back out to name a concrete `make_flush(axis=...)`. A
   structured `axis` field would remove the parse.
4. **Registry injection.** The earlier resolution ("delegate to `mcp_server.build_registry`")
   reverses `ARCHITECTURE.md`'s `scene → orchestration → mcp` arrow. Implemented as
   constructor injection with a function-local deferred import as fallback;
   `src/app/__init__.py` already builds the registry and could pass it in, which would remove
   the fallback. `app/` is main-agent-owned, so that edit was not made here.
5. **`PromotionRefused` is defined locally**, subclassing both `contracts.RuleError` and
   `ValueError`. If `mcp_server` or `viewer` needs to catch it by name it wants promoting into
   `contracts.errors` beside `RunPaused` and `ProposalConflict`.

## Dependencies

`contracts` at module scope. `measure` and `spatial` are imported inside the functions that
use them, and the real `scene.Scene` is imported only by `concurrency_test.py`. `mcp_server`
is deliberately not imported at module scope — see gap 4.

## Testing

`pytest src/orchestration` from the repo root. Most files use the local `scene` fixture (a
`FakeScene` backed by a real `contracts.SceneDocument`, never a mock that records calls);
`concurrency_test.py` drives the real `scene.Scene` over a real `testing.FakeEngine` from real
threads, because a double cannot exhibit an interaction it does not implement. See `CLAUDE.md`
for exact commands and status.
