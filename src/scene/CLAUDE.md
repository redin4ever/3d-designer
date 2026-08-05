# scene — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever writes the bodies of the stubs here.

## Status

**RED by design.** Every method in `document.py`, `history.py`, `cache.py`, `events.py`
and `persistence.py` raises `NotImplementedError("scene.<name>: not implemented")`.
`Scene.__init__` and the `document` property (`__init__.py`) are real, already-working
code — they are not stubs.

Currently **31 tests, 1 green, 30 red**:

- Green: `events_test.py::test_scene_source_never_imports_the_viewer`. It parses every
  source file in this package with `ast` and asserts none of them import anything named
  `viewer` — it never constructs a `Scene` or calls a method, so it does not depend on any
  stub being implemented.
- Red: everything else, all failing with `NotImplementedError` (a handful of tests wrap a
  call in `pytest.raises(SomeOtherError)`, which does not catch `NotImplementedError` — it
  propagates past the `with` block, so those tests are red for the same underlying reason,
  just surfaced as an uncaught exception rather than a caught-wrong-type failure).

A change that makes the red count anything other than 0 or 30 needs an explanation in the
commit message.

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
  second one.** `Operation.placements`/`joinery`/`acceptance` are a known, documented gap
  (nested dataclasses not yet given a serialised shape); no test in this package exercises
  an operation carrying any of the three, so do not block a `save`/`load` implementation
  on solving that — extend the documented shape when it is actually needed.
- **Do not depend on `src/ops/`, `src/align/`, `src/gaps/`, `src/detail/`, or `src/uv/`.**
  None of them exist yet. If a future change seems to need one, that dependency belongs in
  whatever module assembles the real `HandlerRegistry`, not in `scene` itself.

## Test layout

Mirrors the five responsibility files, one test file each, plus fixtures shared across all
of them in `conftest.py`:

| Test file | Covers |
|---|---|
| `document_test.py` | determinism, basic apply (including the `delete_object` handler), the write lock, the failure contract |
| `history_test.py` | undo, redo, the undo-past-the-beginning policy, truncate-on-append, undo barriers, checkpoints |
| `cache_test.py` | `snapshot_of` identity caching, `invalidate_cache` staleness/freshness |
| `events_test.py` | `subscribe`/unsubscribe, listener isolation, the static viewer-import check |
| `persistence_test.py` | save/load round trip, the newer-`schema_version` failure |

A new case for an existing method's contract gets added to the matching file, not a new
top-level test file, unless it grows enough to need its own split (split the source file
the same way first, per `.claude/rules/modularity.md`).

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/contracts/contracts_test.py` and `src/raw/raw_test.py`: dataclasses over
dicts, `from __future__ import annotations`, and a docstring on every test stating the
product-level consequence of the test failing — not just what it checks.

## A note on this environment

This pass was written and reviewed without a working Python interpreter available in the
sandbox (`python`/`python3` resolve to the Windows Store alias stub only — see the root
`CLAUDE.md`'s "Environment facts"). Every file was hand-checked for balanced
parentheses/brackets/triple-quotes and for import correctness against
`src/contracts/__init__.py`'s actual export list, but `pytest src/scene` has not been
executed. Run it first thing in any environment that does have Python 3.13 and treat a
collection error (as opposed to the expected `NotImplementedError`/assertion failures) as
a defect in this pass, not in the implementation to come.
