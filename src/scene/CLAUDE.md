# scene — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Every function here is implemented and its suite passes, run against a real
Python 3.13. Built test-first throughout (Rule 4) — including the three post-QA defect
fixes below, each of which was reproduced as a failing test first:

| Defect | What it was | Where the fix lives |
|---|---|---|
| F-010 | One operation against pre-existing geometry made `undo`/`redo`/`rollback_to` raise for the rest of the session | `targets.py` (reject early), `document.py::_run_operations` (survive anyway) |
| F-011 | Undo across a raw-execution barrier re-ran the script instead of restoring it | `geometry_snapshot.py`, `barriers.py`, `document.py::_restore_nearest_state` |
| F-012 | Save/reload silently dropped every constraint, joinery intent and acceptance query | `op_codec.py`, schema version 2 in `persistence.py` |


## Commands

```bash
# this module only
pytest src/scene -q

# one file
pytest src/scene/history_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

## Ownership

`src/scene/**` only, per `.pipeline/modules.json`. `.pipeline/modules.json` lists
`ops`/`align`/`gaps`/`detail`/`uv` as this module's eventual, design-time dependencies —
**none of them exist yet**, and this module must not import any of them. Tests build two
tiny fake handlers in `conftest.py` instead (`add_cube`, `delete_object`, plus `boom` for
the failure-path tests). When those sibling modules exist, `scene` itself still does not
import them directly — a caller (eventually `orchestration` or `mcp`) assembles the real
`HandlerRegistry` and hands it to `Scene.__init__`; `scene` only ever sees the
`HandlerRegistry` protocol.

`src/contracts/`, `src/testing/`, and the root `conftest.py` are frozen surfaces owned
elsewhere (Rule 5) — read them, never edit them. Nothing in this pass needed a contract
request; everything `scene` needs (`SceneDocument`, `Operation`, `HandlerRegistry`,
`ChangeKind`, `SceneChangeEvent`, `Checkpoint`, `UndoBarrier`, `WriteLease`,
`LockContention`, `EngineProtocol`, `MeshSnapshot`, `SCHEMA_VERSION`) already exists.

## Conventions specific to this module

- **`__init__.py` assembles `Scene` from five mixins and holds the constructor.** This is
  a deliberate, documented departure from "barrel: re-exports only" — a class needs a
  constructor and there is nowhere else for it to live without an unrequested sixth file.
  All *behaviour* still lives in `document.py`/`history.py`/`cache.py`/`events.py`/
  `persistence.py`. If `__init__.py` ever grows logic beyond composition and field
  initialisation, that logic belongs in one of the five files instead.
- **The five mixins are the only behaviour; the four helper modules are collaborators
  they call.** `targets.py`, `barriers.py`, `geometry_snapshot.py` and `op_codec.py` hold
  no `Scene` state and are not mixed in — they exist because `apply`, `replay` and `save`
  each grew a second responsibility, and Rule 2 says split at the seam rather than at a
  line number. `replay_report.py` is data shapes only.
- **Mixins share `self` by convention, not by a declared Protocol.** Every mixin's
  docstring says which private attributes it expects (`_engine`, `_handlers`,
  `_document`, `_cache`, `_listeners`) — all set once, in `Scene.__init__`. Do not add a
  new private attribute without updating the mixin docstring that relies on it.
- **`apply()` must pre-validate before calling the handler.** Duplicate `op_id` and an
  opaque op with no `snapshot_path` are both things `SceneDocument.append` already
  rejects; check for them (or otherwise guarantee the append will succeed) *before* the
  handler runs, never after. See `document.py`'s `apply` docstring, point 3, and
  `document_test.py::test_apply_of_an_opaque_op_without_a_snapshot_path_fails_before_touching_the_engine`.
- **`replay()` never emits, `undo`/`redo`/`rollback_to` emit exactly one event.**
  `replay()` is the low-level "rebuild everything" primitive; the three history methods
  are what decide `ChangeKind.ROLLBACK` vs `ChangeKind.FULL_RESYNC` and tell listeners.
  Do not have `replay()` itself emit — a caller invoking it directly (e.g. after `load()`)
  is not describing an undo/redo/rollback and has no single `ChangeKind` to report.
- **`replay()` skips what it cannot re-run; it never aborts.** It returns a
  `ReplayReport`, and every skip is carried to the caller twice over — on
  `Scene.last_replay` and in the emitted event's `log_line`. Both are required, not
  belt-and-braces: a rebuild that quietly dropped operations leaves the operator looking
  at a scene that appears whole. If you add a new failure mode inside `_run_operations`,
  add a `SkippedOperation` for it; never `raise` and never `pass`.
- **Nothing may re-execute an opaque operation.** Every rebuild goes through
  `_restore_nearest_state`, which restores the closest captured geometry at or before the
  target head and replays only what follows. `apply` captures *both* sides of every
  barrier (`barriers.py`): a pre-execution capture alone is enough to undo across one and
  not enough to redo forward over it. `capture_snapshot` writes geometry via
  `EngineProtocol` — never `save()`, which serialises the log an opaque operation is by
  definition not described by.
- **`apply` refuses an operation whose target no logged operation produced** and that was
  not in the engine when the `Scene` was constructed (`targets.py`, rule
  `scene.unknown_target`). Objects present at construction are legitimate —
  `build_app(reset_scene=False)` is supported — and are recorded by the constructor. The
  ledger is updated incrementally on `apply` and recomputed from the log whenever the head
  moves, because undo genuinely removes objects.
- **What an operation produced is stored on the log entry.** `apply` appends
  `replace(op, produced_objects=..., status=APPLIED)` rather than `op` itself: the
  `OperationResult` is gone after the call, and the log has to answer "could this scene
  rebuild that object" on its own, including after a save and reload.
- **Barrier-crossing math is a half-open interval check**, not a membership test on a
  single index: undoing from `old_head` to `new_head` crosses a barrier iff
  `new_head <= b.index < old_head` for some barrier `b`; redo and `rollback_to` are the
  same check with the interval's direction/endpoints adjusted — see each method's
  docstring in `history.py` for the exact bounds. Get this backwards and every
  barrier-adjacent undo/redo silently reports the wrong `ChangeKind`.
- **The cache stores the object itself, not a copy.** `snapshot_of` returning `x is y` on
  a repeat call (no invalidation in between) is part of the contract, not an incidental
  implementation detail — see `cache_test.py::test_snapshot_of_returns_the_same_object_on_repeat_calls`.
- **`_emit` swallows listener exceptions individually, not with one try/except around the
  whole loop.** A `try`/`except` wrapping the entire delivery loop would let the first
  raising listener stop every listener after it from being called — see
  `events_test.py::test_other_listeners_still_receive_the_event_when_one_raises`, which
  specifically catches that shortcut.
- **Persistence format is fixed in `persistence.py`'s module docstring — do not invent a
  second one.** It is at **schema version 2** (ADR-015) and round-trips *every* field of
  `Operation`, nested dataclasses included; the per-operation shape lives in `op_codec.py`.
  The earlier note here called `placements`/`joinery`/`acceptance` "a known, documented
  gap" and deferred them because no test exercised one. That reasoning was right for a
  module built in isolation and wrong for a shipped product: the gap was invisible until
  the first reload, and every file written before the fix was written wrong. If you add a
  field to `Operation`, add it to `op_codec.py` in the same change — nothing else will
  catch you.
- **Version handling is asymmetric on purpose.** Newer than `SCHEMA_VERSION` and older
  than `MIN_READABLE_SCHEMA` are both refusals; anything in between opens with a
  `UserWarning` naming what the file never stored. Do not downgrade that warning to a log
  line: a v1 scene reloads looking intact and has silently lost the reason for its
  geometry, and this is the only moment anyone can be told. Note the repo's pytest config
  turns `DeprecationWarning` into an error — use `UserWarning`.
- **Do not depend on `src/ops/`, `src/align/`, `src/gaps/`, `src/detail/`, or `src/uv/`.**
  None of them exist yet. If a future change seems to need one, that dependency belongs in
  whatever module assembles the real `HandlerRegistry`, not in `scene` itself.

## Test layout

Mirrors the five responsibility files, one test file each, plus fixtures shared across all
of them in `conftest.py`:

| Test file | Covers |
|---|---|
| `document_test.py` | `ScenePort` conformance, determinism, basic apply (including the `delete_object` handler), the write lock, the failure contract, target validation, replay skip-and-report |
| `history_test.py` | undo, redo, the undo-past-the-beginning policy, truncate-on-append, undo barriers, checkpoints, barrier restore vs re-run, the mixed pre-existing/logged history cycle |
| `cache_test.py` | `snapshot_of` identity caching, `invalidate_cache` staleness/freshness |
| `events_test.py` | `subscribe`/unsubscribe, listener isolation, the static viewer-import check |
| `persistence_test.py` | save/load round trip of every `Operation` field, the v1 warning, the too-old and too-new `schema_version` refusals |

`conftest.py` carries the handler `random_object`, which produces a differently-named
object on **every call**. That is deliberate and it is the only handler that can tell a
snapshot restore apart from a silent re-run — a deterministic one produces identical
geometry either way, which is exactly why F-011 survived a green suite. It uses a counter
rather than `uuid4`, so every call differs while every run stays reproducible.

A new case for an existing method's contract gets added to the matching file, not a new
top-level test file, unless it grows enough to need its own split (split the source file
the same way first, per `.claude/rules/modularity.md`).

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/contracts/contracts_test.py` and `src/raw/raw_test.py`: dataclasses over
dicts, `from __future__ import annotations`, and a docstring on every test stating the
product-level consequence of the test failing — not just what it checks.

## A note on this environment

There **is** a working interpreter, contrary to what this file used to say. It is at
`%LOCALAPPDATA%\Programs\Python\Python313\python.exe` — the bare `python` on PATH is the
Windows Store alias stub and runs nothing, which is what the earlier note mistook for
having none. Every suite in this module has been executed against it:

```bash
PYTHONIOENCODING=utf-8 "$LOCALAPPDATA/Programs/Python/Python313/python.exe" -m pytest src/scene -q
```

Set `PYTHONIOENCODING=utf-8`: this module's docstrings and several test names contain
characters the default Windows console codepage (cp1252) cannot encode, and without it
pytest's own output raises rather than the tests failing.

## Known limitations, recorded rather than discovered later

- **A geometry snapshot restores meshes, transforms and material *slot names* — not PBR
  values, UV layouts, or the pre-triangulation face count.** `MeshSnapshot` does not carry
  the first two, and `EngineProtocol.snapshot` hands over triangles, so a restored mesh is
  the triangulated form of the captured one. This only affects geometry restored across a
  barrier, where the alternative is re-running arbitrary code.
- **Snapshots live in the system temp directory and are never garbage-collected.** They
  are session-scoped rebuild aids, and a rebuild whose snapshot has been cleaned away
  degrades to a replay (which reports the opaque operation as skipped) rather than
  failing. Nothing yet deletes them at the end of a session.
- **Geometry that was in the engine when the scene was opened is a legal target but
  cannot be rebuilt.** It is not captured at construction, so the first rebuild loses it
  and says so in the `ReplayReport`. Capturing a whole `.blend` at startup is a real cost
  decision and belongs at a gate, not in a defect fix.
