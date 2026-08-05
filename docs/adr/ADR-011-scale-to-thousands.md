# ADR-011 — Built for thousands of objects: spatial index and incremental live view

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 11.4, 5.1, 5.3, 3.1, 4.1

## Decision

The system targets **a full game level or district — thousands of objects** (Gate A 11.4). Three
things follow and are treated as architecture rather than optimisation:

1. **A spatial index (BVH) over the scene**, rebuilt incrementally. Clipping and proximity
   queries are broad-phase-pruned before any triangle test.
2. **Incremental live-view updates over WebSocket** — node transforms and changed mesh buffers
   only. Never a full glTF re-export per change.
3. **Scoped checks.** Gate A 3.1 runs geometry checks after every geometry-changing operation.
   At thousands of objects, whole-scene validation per call is not viable, so checks run against
   the **changed objects and their spatial neighbours**, with full-scene validation reserved for
   phase boundaries and export.

## Context

Gate A 5.1 and 5.3 require a live 3D view with the latest change highlighted, and 4.1 requires a
per-action response carrying measurements. Both are cheap at 50 objects and impossible at 5,000
if implemented naively.

Research found no production-ready incremental glTF or USD streaming format. The realistic options
are full GLB reload per checkpoint (~1–3 s, correctness-guaranteed) or a custom WebSocket diff
protocol applying changes directly to live `BufferGeometry` (sub-200 ms, topology-preserving edits
only). At this scale the second is required, with full reload retained as the correctness fallback
and the resync path after any non-topology-preserving edit.

## Consequences

- The BVH is a **maintained structure with an invalidation contract**, not a per-call rebuild.
  Getting its invalidation wrong produces stale clipping results, which is a silent-wrong-answer
  failure — so it gets direct tests, not just integration coverage.
- Broad-phase pruning does not solve everything: **non-convex mesh-mesh penetration depth is
  unsolved** in the general case (FCL returns 0 depth on genuine contact). The tool reports
  *overlap and its extent along a separating axis*, and does not claim a true penetration depth
  it cannot compute.
- The WebSocket protocol needs a resync path. Any operation that changes topology, and any raw
  code execution (ADR-009), forces a full re-send for the affected objects.
- ADR-002's per-operation geometry cache is what keeps undo re-evaluation (ADR-006) tractable at
  this scale.

## Superseded by

Nothing.
