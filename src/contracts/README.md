# contracts — the frozen shared surface

Every module compiles against these types. That is what made sixteen modules buildable in
parallel: they were not coordinating, they were compiling against the same frozen surface.

## The one that matters most

**`EngineProtocol`** (`engine.py`) is the sole typed boundary between `bpy` and everything
else. `src/engine/` is the only module permitted to import Blender; every other module is
written against this Protocol and handed an implementation at the composition root.

Three consequences, all load-bearing:

1. The entire decision layer runs its tests in a tenth of a second with no Blender.
2. `dependsOn` becomes an *integration* order rather than a build queue — which is why the
   seven-deep dependency chain did not serialise the build.
3. A Blender version bump touches one module's internals instead of fifteen call sites, and
   Blender ships breaking Python API changes with no deprecation policy.

## Files

| File | Holds |
|---|---|
| `geometry.py` | `Vec3`, `Quat`, `Transform`, `AABB`, `MeshSnapshot`, `EPSILON` |
| `engine.py` | `EngineProtocol` and its six operation groups; `EngineError`, `RepairOutcome` |
| `measurement.py` | 7 metric kinds, 10 defect classes, `AcceptanceQuery`, `DEFAULT_SEVERITY` |
| `constraints.py` | the 12-type constraint vocabulary, `Anchor`, `Placement` |
| `operations.py` | `Operation`, `OperationHandler`, `ToolSpec`, `ToolRole`, `ActionReport`, `JoineryIntent` |
| `scene_doc.py` | `SceneDocument` and its validated mutators, `Checkpoint`, `UndoBarrier` |
| `phases.py` | `Phase`, `CheckCadence`, `WriteLease`, `WriteLockManager`, `Conflict` |
| `export_profiles.py` | the four engine profiles — data only, no conversion logic |
| `wire.py` | the WebSocket protocol shared by `viewer` and `frontend` |

## Types here enforce their own invariants

This is deliberate and it was earned. Two independent reviewers attacked the first draft
before any module was built against it and found 15 blockers — states that were
representable and must never exist. Each is now impossible to construct, and
`contracts_test.py` carries a regression test named after the failure it prevents:

- An `AABB` could be built inverted, which short-circuits `overlaps()` to `False` on the
  first inverted axis — a *false negative* in the broad-phase test that feeds clipping
  detection.
- `SceneDocument.head` could go negative, which slices from the end and silently drops the
  last operation instead of raising.
- An opaque (non-replayable) operation could exist with no undo barrier, letting rollback
  attempt a replay across code that cannot be replayed.
- Appending after an undo did not truncate, so a later redo replayed stale work.
- `WriteLease` was freely constructible, so "exactly one writer" was unenforceable — two
  agents each holding a lease they built themselves is not a lock.
- `MeasurementReport` could claim a scope it never examined, defeating the one thing the
  field exists for.

If a validation here feels pedantic, read the test named after it. Each one is a bug that
was reachable.

## Changing it

**No module agent edits this.** A module needing a change appends to
`.pipeline/contract-requests.json` and adapts locally; the main agent reconciles between
rounds. An error here is multiplied by every module that compiled against it.
