# viewer — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever touches this module next.

## Status

**GREEN.** `ViewerBridge` (`bridge.py`, assembled from `TranslateMixin`/`translate.py`
and `ClientMixin`/`client.py`), `snapshot_to_payload`/`transform_payload`
(`payloads.py`), and `serve`/`ViewerTransportUnavailable` (`server.py`) are all
implemented. `pytest src/viewer -q` passes 31/31; `pytest src -q` (whole decision layer)
also passes with no regressions in `scene` or `orchestration`.

Written test-first per Rule 4: every source file started as a signature plus a
`NotImplementedError("viewer.<name>: not implemented")` body, the full 31-test suite was
run and confirmed red on that exception (never `ImportError` — no stub was missing an
import or a name), and only then were the bodies filled in.

## Commands

```bash
# this module only
pytest src/viewer -q

# one file
pytest src/viewer/bridge_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker anywhere in this module — nothing here imports `bpy`, and
nothing here needs a real socket either (`serve()`'s network path is lazily imported;
see "Contract gaps" in `README.md`, item 4).

## Boundaries

- Write only inside `src/viewer/**`. `src/contracts/`, `src/scene/`, `src/orchestration/`,
  `src/testing/`, and the root `conftest.py` are frozen surfaces owned elsewhere (Rule
  5) — read them, never edit them.
- `scene` must never import `viewer`. This module is the one place in the pipeline that
  is *allowed* to import both `scene` and `orchestration` — that asymmetry is the whole
  point (`contracts.SceneChangeEvent`'s own docstring), so do not "fix" it by adding a
  callback from `scene`/`orchestration` back into here.
- Do not import `bpy`. `viewer` is two network hops away from `src/engine/` (through
  `scene`) and has no reason to ever need it.
- `viewer/__init__.py` is a pure barrel — re-exports only. Unlike `scene`'s and
  `orchestration`'s `__init__.py`, it does not also hold a class constructor; nothing
  here needed that exception (`ViewerBridge.__init__` is plain composition and lives in
  `bridge.py`, beside the rest of the class it constructs). If `__init__.py` ever grows
  a line of logic, that logic belongs in one of the other files instead.
- Nothing outside `viewer/` may import `viewer.bridge`, `viewer.translate`, etc.
  directly — only `from viewer import <name>`, per `__init__.py`'s `__all__`. Files
  inside this package (its own `*_test.py` files) import fixtures from `conftest.py` the
  normal pytest way (as fixture parameters, never `from .conftest import ...`) — see
  "Style" below.
- `websockets`/`starlette` are declared project dependencies (`pyproject.toml`) **and are
  installed here** — `doctor` reports the version, and `live_socket_test.py` opens a real
  socket against a real client. This note used to say they were missing, which was the
  stated reason for the lazy import and was wrong for a whole pass.
  The practice is still right, for a better reason: `serve()` must stay behind a lazy
  `import websockets` inside the function body so that importing `viewer` — and running
  every other test in this package — works on a machine that does *not* have them. The
  live view is optional; the geometry core is not. Do not hoist that import to module
  level.

## Implementation notes for whoever picks this up next

- **`enumerate_object_ids` (`translate.py`) reaches into `scene._engine` as a documented
  fallback**, because `scene.Scene` has no public "list every object" method — see
  `README.md`'s "Assumptions" item 1 before treating this as an accident. It tries a
  public `list_objects()` on `scene` first; every test double in `conftest.py` (`FakeScene`)
  offers one, so the private-attribute path is only actually exercised by the
  `real_scene` fixture (a genuine `scene.Scene`).
- **`_snapshots_for` (`translate.py`) prefers `event.snapshots`, falls back to
  `scene.snapshot_of`.** Do not simplify this to just one or the other: the real
  `scene.apply()` today never populates `SceneChangeEvent.snapshots` (only `object_ids`),
  while the synthetic events this package's own tests construct for
  `TRANSFORMS_ONLY`/`TOPOLOGY_CHANGED` do populate it directly, matching the documented
  contract ("populated only for kinds needing buffers"). Both paths are covered — see
  `bridge_test.py`'s real-`Scene` tests vs. its `fake_scene`-based `ChangeKind` tests.
- **Two independent try/except layers protect `scene.apply` from a broken viewer**:
  `scene`'s own `_emit` (frozen, not ours) and this module's own
  `_on_scene_change`/`_enqueue`. Do not remove either on the theory that the other makes
  it redundant — `test_a_bridge_whose_queue_raises_does_not_break_scene_apply` in
  `bridge_test.py` is specifically about this module's own defence holding up on its
  own, independent of `scene`'s.
- **`handle_client` always returns exactly the messages produced by that one call**, via
  a queue-length-delta drain (`start = len(self._queue)` ... `self._queue[start:]`), not
  the whole outstanding queue. A scene-driven push queued *before* a client action must
  still be there for the next `pending()` call, not swallowed by an unrelated
  `handle_client`. Keep this invariant if you touch `client.py::handle_client`.
- **`ClientMessage.data`'s shape is this module's own convention, not a frozen one** —
  see `README.md`'s "Assumptions" item 2 before changing how a payload dataclass is
  reconstructed from it. `frontend` (still `planned` in `.pipeline/modules.json`) will
  need to match this exactly; flag any change here for reconciliation.
- **`orchestrator` is optional (`ViewerBridge(scene)` with no second argument).**
  PAUSE/RESUME/REDIRECT/SET_CADENCE without one produce an `ERROR` message, never an
  exception — see `_ensure_orchestrator` in `client.py`. Keep this graceful; a viewer
  attached read-only (no control channel) is a legitimate configuration, not a bug.
- **`ROLLBACK`/`FULL_RESYNC` both degrade to a full resend** rather than the
  finer-grained diff `contracts.ChangeKind.ROLLBACK`'s docstring describes — see
  `README.md`'s "Assumptions" item 3 for exactly why (`scene.history` does not populate
  `object_ids` for either). Safe, not optimal; revisit if `scene` ever starts populating
  them.

## Test layout

Mirrors the source split, one file per responsibility, plus shared fixtures:

| Test file | Covers |
|---|---|
| `payloads_test.py` | `snapshot_to_payload` (flat buffers, multi-material groups), `transform_payload` (quaternion order) |
| `bridge_test.py` | `attach`/`detach`, `full_scene`, `seq` monotonicity, the per-`ChangeKind` wire mapping, the broken-queue-survives-`scene.apply` guarantee |
| `client_test.py` | `handle_client` routing for every `ClientMessageType`, including the missing-orchestrator and malformed-payload edge cases |
| `server_test.py` | `serve()`'s lazy import: raises `ViewerTransportUnavailable` when `websockets` is absent, wires correctly when a `sys.modules`-injected fake is present |
| `conftest.py` | `real_scene` (genuine `scene.Scene` + `testing.FakeEngine`), `fake_scene` (`FakeScene` double — publishes arbitrary `SceneChangeEvent`s on demand), `recording_orchestrator`, `make_snapshot`, `add_cube_op`/`delete_op` |

A new case for an existing method's contract gets added to the matching file, not a new
top-level test file, unless it grows enough to need its own split (split the source file
the same way first, per `.claude/rules/modularity.md`).

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/scene/` and `src/orchestration/`'s own test files: dataclasses over
dicts, `from __future__ import annotations`, and a docstring on every non-trivial test
stating the product-level consequence of the test failing — not just what it checks.
Test doubles record calls (`FakeScene.calls`, `RecordingOrchestrator.calls`) only for
assertions that are inherently about *which call was made* (routing); anything that can
be asserted on real geometry or real state uses the real `scene.Scene` +
`testing.FakeEngine` instead (`real_scene` fixture) — same reasoning as
`testing.FakeEngine`'s own docstring on why it computes real geometry rather than only
recording calls.
