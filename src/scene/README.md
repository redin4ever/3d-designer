# scene

Owns the operation log and turns it into geometry (ADR-002). The log is the source of
truth; geometry is *generated* from it, never the reverse. That is what makes undo a
pointer move rather than a snapshot restore (ADR-006), and what keeps constraints live —
move the stair, and the railing constrained to its outer edge follows.

## Public interface

Everything importable from `scene` is re-exported by `__init__.py`, which is also where
`Scene` itself is assembled out of five mixins (see "Layout" below).

```python
class Scene:
    def __init__(self, engine: EngineProtocol, handlers: HandlerRegistry, *, scene_id: str = "") -> None: ...

    @property
    def document(self) -> SceneDocument: ...   # the live, mutable source of truth

    def apply(self, op: Operation, *, lease: WriteLease | None = None,
              snapshot_path: str = "") -> OperationResult: ...
    def replay(self) -> None: ...                       # rebuild all geometry from the log

    def undo(self, steps: int = 1) -> ChangeKind: ...
    def redo(self, steps: int = 1) -> ChangeKind: ...
    def rollback_to(self, checkpoint: str) -> ChangeKind: ...
    def checkpoint(self, name: str, note: str = "") -> Checkpoint: ...

    def snapshot_of(self, object_id: str) -> MeshSnapshot: ...   # cached
    def invalidate_cache(self, object_id: str) -> None: ...

    def subscribe(self, listener: Callable[[SceneChangeEvent], None]) -> Callable[[], None]: ...

    def save(self, path: str) -> None: ...
    @staticmethod
    def load(path: str, engine: EngineProtocol, handlers: HandlerRegistry) -> "Scene": ...
```

## Layout

One file per responsibility, each a mixin `Scene` inherits from; `__init__.py` assembles
them and holds the constructor (see its module docstring for why the constructor lives
there rather than in an unrequested sixth file):

| File | Owns |
|---|---|
| `document.py` | `apply`, `replay` — turning the log into geometry |
| `history.py` | `undo`, `redo`, `rollback_to`, `checkpoint` — moving the pointer |
| `cache.py` | `snapshot_of`, `invalidate_cache` — reading geometry cheaply |
| `events.py` | `subscribe`, `_emit` — what the live view subscribes to |
| `persistence.py` | `save`, `load` — round-tripping the document to disk |

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
`ChangeKind.FULL_RESYNC` instead of `ChangeKind.ROLLBACK` — replaying across code that
cannot be replayed produces wrong geometry with no error, which is the exact failure a
barrier exists to make visible instead. See `history_test.py`'s barrier tests.

### Persistence format

A single JSON document; the exact shape is fixed in `persistence.py`'s module docstring.
`active_lease` is deliberately **not** persisted — a lease proves one specific run holds
the lock, and a reload starts with no lock held, like any other freshly constructed
`Scene`. A file whose `schema_version` is newer than `contracts.SCHEMA_VERSION` must fail
`load()` loudly with a `ValueError` mentioning `"schema_version"`, never silently misread.

## Testing

Fake handlers (`add_cube`, `delete_object`, `boom`) live in `conftest.py`, local to this
package, so `scene` is fully testable without `src/ops/` existing (`.pipeline/modules.json`
lists it only as an eventual, design-time dependency). Every test uses the root `engine`
fixture (a `FakeEngine`) plus this package's own `handlers`/`add_cube_op`/`delete_op`
fixtures.

```
pytest src/scene
```

See `CLAUDE.md` for the current red/green count and local conventions.

## Dependencies

`src/contracts/` only, at import time (frozen surface — read, never edited; see
`.pipeline/contract-requests.json` for anything genuinely missing, which as of this pass
is nothing). `src/testing/` (`FakeEngine`) in tests only. No `bpy`, ever. **Never**
`src/viewer/` — checked statically, see `events_test.py`.
