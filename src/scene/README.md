# scene

Owns the operation log and turns it into geometry (ADR-002). The log is the source of
truth; geometry is *generated* from it, never the reverse. That is what makes undo a
pointer move rather than a snapshot restore (ADR-006), and what keeps constraints live —
move the stair, and the railing constrained to its outer edge follows.

## Public interface

Everything importable from `scene` is re-exported by `__init__.py`, which is also where
`Scene` itself is assembled out of five mixins (see "Layout" below).

`Scene` satisfies `contracts.ScenePort`, and `document_test.py::
test_the_real_scene_satisfies_the_declared_scene_port` is what keeps that true rather than
merely intended.

```python
class Scene:
    def __init__(self, engine: EngineProtocol, handlers: HandlerRegistry, *, scene_id: str = "") -> None: ...

    @property
    def engine(self) -> EngineProtocol: ...    # read-only; measurements run against it
    @property
    def document(self) -> SceneDocument: ...   # the live, mutable source of truth
    @property
    def last_replay(self) -> ReplayReport: ... # what the most recent rebuild managed

    def apply(self, op: Operation, *, lease: WriteLease | None = None,
              snapshot_path: str = "") -> OperationResult: ...
    def replay(self) -> ReplayReport: ...               # rebuild all geometry from the log

    def undo(self, steps: int = 1) -> ChangeKind: ...
    def redo(self, steps: int = 1) -> ChangeKind: ...
    def rollback_to(self, checkpoint: str) -> ChangeKind: ...
    def checkpoint(self, name: str, note: str = "") -> Checkpoint: ...
    def capture_snapshot(self, op_id: str) -> str: ...   # live geometry, to a restorable file

    def snapshot_of(self, object_id: str) -> MeshSnapshot: ...   # cached
    def invalidate_cache(self, object_id: str) -> None: ...

    def subscribe(self, listener: Callable[[SceneChangeEvent], None]) -> Callable[[], None]: ...

    def save(self, path: str) -> None: ...
    @staticmethod
    def load(path: str, engine: EngineProtocol, handlers: HandlerRegistry) -> "Scene": ...
```

Also exported: `ReplayReport`, `SkippedOperation` (`replay_report.py`) and
`UNKNOWN_TARGET_RULE`, the rule name `apply` refuses an unreplayable target with.

## Layout

One file per responsibility, each a mixin `Scene` inherits from; `__init__.py` assembles
them and holds the constructor (see its module docstring for why the constructor lives
there rather than in an unrequested sixth file):

| File | Owns |
|---|---|
| `document.py` | `apply`, `replay` — turning the log into geometry |
| `history.py` | `undo`, `redo`, `rollback_to`, `checkpoint`, `capture_snapshot` — moving the pointer |
| `cache.py` | `snapshot_of`, `invalidate_cache` — reading geometry cheaply |
| `events.py` | `subscribe`, `_emit` — what the live view subscribes to |
| `persistence.py` | `save`, `load` — round-tripping the document to disk |

Plus five collaborators those five call. They hold no `Scene` state and are not mixed in:

| File | Decides |
|---|---|
| `targets.py` | whether an operation could ever be re-run — the `scene.unknown_target` refusal |
| `geometry_snapshot.py` | writing live geometry to a file and reading it back, via `EngineProtocol` alone |
| `barriers.py` | which geometry snapshot describes which position in the log |
| `op_codec.py` | how one `Operation` and its nested dataclasses are serialised |
| `replay_report.py` | the shape of "what the rebuild actually managed" (data only) |

## Status

**GREEN.** Every function here is implemented and its suite passes. This module was built test-first (Rule 4): the tests were written against the contract, run, and confirmed failing on `NotImplementedError` before any body existed.


## Decisions this module makes (the contract does not fix these; tests below pin them)

### Write lock

`apply()` needs a lease **only when a lock is actually held**:

- `document.active_lease is None` (nobody has ever acquired the write lock — genuine
  single-agent use, the common case until `orchestration` exists) → `apply()` proceeds
  regardless of the `lease` argument. This is a deliberate allowance for solo/local runs,
  not a general bypass.
- `document.active_lease is not None` and `lease` is `None` or does not match → raises
  `contracts.LockContention`.

See `document_test.py`'s "write lock" section for all four cases exercised.

### Undo/redo past the bounds of the log

**Raises, does not clamp.** `undo`/`redo` delegate to
`SceneDocument.set_head`, whose own `ValueError` on an out-of-range index is left to
propagate. A clamp would silently turn "undo 5" into "undo 2" with no signal that fewer
steps happened than asked — the same silent-wrong-answer shape `set_head` already
rejects for a raw negative index. See
`history_test.py::test_undo_past_the_beginning_raises`.

### A failed operation

Two distinct failure shapes, both leaving the log **exactly** as it was:

1. **The handler raises.** The exception propagates to the caller unchanged; `apply()`
   never appends, never emits, and never catches it.
2. **The handler returns `OperationResult(ok=False, ...)`.** `apply()` returns that
   result as-is; it still never appends and never emits.

See `document_test.py`'s "failure" section.

### Undo barriers

An opaque operation (raw execution, or any edit that cannot be replayed deterministically)
requires a `snapshot_path` and becomes an `UndoBarrier` — `SceneDocument.append` already
enforces and records this; `scene` only has to route through `append` rather than the raw
list. Undoing, redoing or rolling back **across** one of these returns
`ChangeKind.FULL_RESYNC` instead of `ChangeKind.ROLLBACK`.

That `ChangeKind` is a signal to the viewer, not a rebuild strategy. The rebuild itself
**restores** rather than replays: `apply` captures the live geometry on both sides of every
barrier, and any rebuild starts from the nearest capture at or before the target position
and replays only what follows it. So an opaque operation is never re-executed by an undo,
a redo or a rollback — not only by ones that report `FULL_RESYNC`. Before this, every
rebuild ran from `engine.reset()` through the whole log, and a non-deterministic script
produced different geometry every time while the system reported a clean restore.

A capture the caller hands in is used only if it really is a geometry snapshot; otherwise
`apply` takes its own. `capture_snapshot` must never be `save()` — the log does not
describe what an opaque operation did, which is what makes it opaque.

### A rebuild that cannot complete

`replay()` returns a `ReplayReport` and never aborts. An operation it cannot re-run — a
missing handler, a target that no longer exists, a handler that raises or reports failure,
an opaque operation whose snapshot is gone — is skipped, recorded with the underlying
reason, and the rest of the log still rebuilds. The skips reach the caller on
`Scene.last_replay` and in the emitted event's `log_line`; `log_line` is empty when there
is nothing to report, so a non-empty one always means something happened.

`apply()` refuses, up front, the operation that used to cause this: one naming a target
that no logged operation produced and that was not in the engine when the `Scene` was
constructed. The rule is `scene.unknown_target`. Geometry already present at construction
is legal — `build_app(reset_scene=False)` is a supported workflow — though it cannot be
rebuilt, which the report says rather than hides.

### Persistence format

A single JSON document at **schema version 2**; the exact shape is fixed in
`persistence.py`'s module docstring and the per-operation part in `op_codec.py`. Every
field of `Operation` round-trips, including `placements`, `joinery`, `acceptance`,
`asset_class` and `proposal_id` — v1 dropped all five, so a reloaded scene kept its
geometry and lost the reason for it, which is ADR-002's whole stated payoff (ADR-015).

`active_lease` is deliberately **not** persisted — a lease proves one specific run holds
the lock, and a reload starts with no lock held, like any other freshly constructed
`Scene`. A `schema_version` newer than `contracts.SCHEMA_VERSION`, or older than
`contracts.MIN_READABLE_SCHEMA`, fails `load()` loudly with a `ValueError` mentioning
`"schema_version"`. Anything between the minimum and current opens with a `UserWarning`
naming what the file never stored.

## Testing

Fake handlers (`add_cube`, `delete_object`, `move_object`, `boom`, `random_object`) live
in `conftest.py`, local to this package, so `scene` is fully testable without `src/ops/`
existing (`.pipeline/modules.json` lists it only as an eventual, design-time dependency).
Every test uses the root `engine` fixture (a `FakeEngine`) plus this package's own
`handlers`/`add_cube_op`/`delete_op`/`move_op`/`random_object_op` fixtures.

`random_object` is non-deterministic on purpose: it is the only handler whose output can
distinguish a snapshot restore from a silent re-run, and a deterministic one produces the
same geometry either way — which is precisely how the re-run defect survived a green suite.

```
pytest src/scene
```

See `CLAUDE.md` for the current red/green count and local conventions.

## Dependencies

`src/contracts/` only, at import time (frozen surface — read, never edited; see
`.pipeline/contract-requests.json` for anything genuinely missing, which as of this pass
is nothing). `src/testing/` (`FakeEngine`) in tests only. No `bpy`, ever. **Never**
`src/viewer/` — checked statically, see `events_test.py`.
