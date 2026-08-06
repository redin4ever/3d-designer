# viewer

The Python half of the live view (ADR-011: "incremental live-view updates over
WebSocket — node transforms and changed mesh buffers only, never a full glTF re-export
per change"). Subscribes to `scene`'s change events, translates them into the frozen
wire protocol (`src/contracts/wire.py`), and routes inbound operator control messages
(pause/resume/rollback/redirect/cadence) to `scene`/`orchestration`.

`scene` never imports `viewer` — the dependency arrow points one way
(`contracts.SceneChangeEvent`'s own docstring), which is what lets the viewer crash, be
disabled, or be rebuilt without touching the geometry core. This module's own tests never
construct a `Scene`/`Orchestrator` in a way that would create a cycle; `viewer` is the
only one of the two that is allowed to know the other exists.

## Public interface

Everything importable from `viewer` is re-exported by `__init__.py`, a pure barrel — no
logic lives there, unlike `scene`'s and `orchestration`'s `__init__.py` (which each also
hold their class's constructor for the reason their own module docstrings give). Nothing
here needed that exception: `ViewerBridge`'s constructor is pure composition and lives in
`bridge.py` beside the rest of the class.

```python
class ViewerBridge:
    def __init__(self, scene, orchestrator=None) -> None: ...

    def attach(self) -> None: ...     # subscribes to scene; idempotent
    def detach(self) -> None: ...     # unsubscribes; safe to call when not attached

    def full_scene(self) -> ServerMessage: ...          # every object currently in the engine
    def pending(self) -> tuple[ServerMessage, ...]: ...  # drains the outbound queue
    def handle_client(self, msg: ClientMessage) -> tuple[ServerMessage, ...]: ...

    @property
    def seq(self) -> int: ...         # last sequence number this bridge assigned

def snapshot_to_payload(snap: MeshSnapshot) -> MeshPayload: ...
def transform_payload(snap: MeshSnapshot) -> TransformPayload: ...

def serve(scene, orchestrator, *, host="127.0.0.1", port=8766) -> object: ...

class ViewerTransportUnavailable(RuntimeError): ...   # serve() with no websockets installed
```

## Layout

One file per responsibility, mirroring `scene`'s and `orchestration`'s split:

| File | Owns |
|---|---|
| `payloads.py` | `snapshot_to_payload`, `transform_payload` — the boundary conversion into flat wire buffers |
| `translate.py` | `TranslateMixin` — one `contracts.SceneChangeEvent` → zero or one wire message; `enumerate_object_ids` |
| `client.py` | `ClientMixin` — one `contracts.ClientMessage` → the call it routes to and the messages it produces |
| `bridge.py` | `ViewerBridge` itself: construction, `attach`/`detach`, the outbound queue, the `seq` counter |
| `server.py` | `serve` — the lazy-imported WebSocket transport, and `ViewerTransportUnavailable` |
| `conftest.py` | test-only — `real_scene`/`fake_scene`/`recording_orchestrator` fixtures, not part of the public interface |

`ViewerBridge` is assembled from `TranslateMixin` and `ClientMixin` in `bridge.py`,
exactly the "one class assembled from responsibility mixins, each in its own file" shape
`scene.Scene` and `orchestration.Orchestrator` already use.

## Decisions this module makes (the contract does not fix these)

### Wire mapping per `ChangeKind`

- `TRANSFORMS_ONLY` → `TRANSFORM_UPDATE`, transforms only, **no mesh buffers** — the
  cheap path ADR-011 exists for.
- `OBJECTS_ADDED` / `OBJECTS_MODIFIED` / `TOPOLOGY_CHANGED` → `MESH_UPSERT`, buffers
  resent. The real `scene.apply()` today only ever emits `OBJECTS_ADDED` /
  `OBJECTS_MODIFIED` / `OBJECTS_REMOVED` (see "Assumptions" below); `TRANSFORMS_ONLY` and
  `TOPOLOGY_CHANGED` are handled anyway because `contracts.SceneChangeEvent` — not
  `scene`'s current implementation — is viewer's actual dependency surface, and a future
  `scene` revision emitting either must not require a matching `viewer` change.
- `OBJECTS_REMOVED` → `OBJECTS_REMOVED`, object ids only.
- `FULL_RESYNC` / `ROLLBACK` → a fresh `full_scene()`-equivalent resend. Both are
  degraded to the same safe, correctness-preserving fallback — see "Assumptions".
- `PHASE_CHANGED` → a `PHASE` message when `event.phase` is set; `CHECKPOINT` and any
  other kind produce nothing. Neither is required by this module's brief and nothing
  downstream currently reads them.

### Snapshot sourcing

`_snapshots_for` prefers `event.snapshots` when the emitter populated it (the documented
contract: "populated only for kinds needing buffers") and falls back to
`scene.snapshot_of(object_id)` per id otherwise — which is what makes this module work
against the real, current `scene.apply()` (whose emitted events carry ids but not
snapshots) *and* against a future emitter that populates `snapshots` directly, with no
`viewer` change either way.

### A broken viewer must not break `scene`

Two independent layers, not one relying on the other:

1. `scene`'s own `_emit` (`src/scene/events.py`) already calls every listener inside its
   own `try/except`, so one raising listener cannot stop delivery to the rest or escape
   into `scene.apply`'s caller.
2. `ViewerBridge._on_scene_change` wraps `_translate` in its own `try/except`, and
   `_enqueue` wraps the queue append in another. This module does not rely on layer 1
   alone — a `ViewerBridge` used outside `scene`'s own subscription mechanism (a test, a
   future direct caller) gets the same guarantee independently.

`handle_client` mirrors this on the inbound side: a malformed client payload becomes one
`ERROR` message, never a propagated exception.

### `seq`

One counter, owned by `ViewerBridge`, incremented every time this module constructs a
`ServerMessage` — never read from or set by a caller. Starts at `0` (`ViewerBridge.seq`'s
initial value agrees with `contracts.ServerMessage.seq`'s own default), so an unsent
bridge and an unset message read the same.

## Assumptions (would be contract requests if `src/contracts/` and `src/scene/` were not
frozen surfaces owned elsewhere — Rule 5)

1. **`scene.Scene` has no public "list every current object id" method.** Its interface
   is the operation log and the per-object cache, not an index of what currently exists,
   and the stored `Operation.produced_objects`/`removed_objects` are not reliably
   populated on the log entry `SceneDocument.append` actually stores (`document.py`
   appends `op` itself, not `result`). `full_scene()`/`FULL_RESYNC` need ground truth for
   "every object", so `translate.enumerate_object_ids` falls back to the private
   `scene._engine` attribute `Scene.__init__` stores, preferring a public
   `list_objects()` first if the object offers one (every test double here does). A
   `Scene.list_objects()` derived from `self._engine.list_objects()` would remove the
   need for this fallback entirely.
2. **`ClientMessage.data`'s payload shape.** `wire.py` documents each `ClientMessageType`
   as carrying a typed payload (`RollbackTarget`, `RedirectPayload`, `CadencePayload`)
   but `ClientMessage.data` is a plain `dict[str, Any]` with no specified nesting. This
   module's chosen convention: `data`'s keys are exactly that payload dataclass's
   constructor kwargs (e.g. `{"steps": 3}`, `{"text": "..."}`, `{"cadence":
   "phase_boundaries"}`), reconstructed via `Payload(**msg.data)`. `frontend` must
   encode client messages this way for `handle_client` to route them correctly.
3. **`ROLLBACK`/`FULL_RESYNC` degrade to a full resend.** `contracts.ChangeKind.ROLLBACK`'s
   own docstring says the viewer should "apply it as a normal add/remove/modify diff",
   but `scene.history`'s `undo`/`redo`/`rollback_to` emit
   `SceneChangeEvent(kind=..., head=...)` with no `object_ids` at all — there is nothing
   to diff against. Resending everything is always correct, just not always cheap;
   `scene` populating `object_ids` for a non-barrier-crossing rollback would let this
   module do the cheaper diff the docstring describes.
4. **`serve()`'s connection loop is not covered by this package's own tests.** Neither
   `websockets` nor `starlette` is installed in this environment despite both being
   listed in `pyproject.toml`'s `dependencies`. `serve()` stays behind a lazy import
   (`server_test.py` proves both the "not installed" and, via a `sys.modules`-injected
   fake module, the "installed" wiring path) so the rest of `src/viewer` needs neither
   package to be tested — but the real `async for websocket in ...` loop in
   `server.py::_handle_connection` has only been read-reviewed, not exercised.

## Testing

```bash
# this module only
pytest src/viewer -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

31 tests, all green. No `needs_blender` marker anywhere in this module — everything here
runs against `testing.FakeEngine` (via a real `scene.Scene`) or the local doubles in
`conftest.py`, with no Blender and no real network stack.

## Dependencies

`contracts` at import time (frozen surface — read, never edited). `scene` and
`orchestration` at import time too — this is the one module in the pipeline whose whole
purpose is depending on both (`.pipeline/modules.json`'s `dependsOn`). `testing`
(`FakeEngine`) in tests only. `websockets` only inside `serve()`, imported lazily so the
rest of this package needs neither it nor a real socket to be tested. No `bpy`, ever.
