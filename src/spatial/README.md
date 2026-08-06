# spatial

A maintained BVH (bounding volume hierarchy) over scene objects, answering broad-phase
proximity questions: what's near what, what overlaps what, what's inside a region. It is
the thing that makes clipping detection and scoped validation affordable once a scene has
thousands of objects instead of dozens (ADR-011, Gate A 11.4).

This module owns exactly one class, `SpatialIndex`, over `EngineProtocol`. It never
imports `bpy` — it is testable end to end against `FakeEngine`, like every module outside
`src/engine/` (ADR-008).

## Why this is its own module

A per-call rebuild would be simple and always correct, and was rejected on purpose. At
scale it is too slow to run after every geometry-changing operation, so `SpatialIndex` is
a structure that persists across operations and is updated incrementally.

That trade buys performance and creates exactly one risk: **getting invalidation wrong is
a silent wrong answer.** A stale bounding box looks exactly like a correct one — it is a
well-formed `AABB`, it participates in queries normally, and nothing about the result
shape signals that the object it describes moved three operations ago. This is why the
module gets direct unit tests instead of relying on integration coverage further up the
stack to happen to exercise the right sequence of edits.

## Public interface

Everything importable from `spatial` is re-exported by `__init__.py`:

```python
class SpatialIndex:
    def __init__(self, engine: EngineProtocol) -> None: ...

    def rebuild(self) -> None: ...
        # Full rebuild from engine.list_objects(). The only operation guaranteed to
        # leave zero stale entries no matter what came before it.

    def insert(self, object_id: str) -> None: ...
        # Add one newly-created object. Must not require a rebuild to be queryable.

    def update(self, object_id: str) -> None: ...
        # The object moved or changed shape. Bounds are re-read from the engine
        # immediately — the caller does not also need to call invalidate().

    def remove(self, object_id: str) -> None: ...
        # The object is gone. It must not appear in any later query result, and
        # bounds_of() on its id must fail identifiably rather than return a stale box.

    def invalidate(self, object_id: str) -> None: ...
        # Mark stale WITHOUT re-reading yet. The next query touching this id must not
        # return stale bounds — the read happens lazily, at query time, not here.

    def bounds_of(self, object_id: str) -> AABB: ...

    def nearby(self, object_id: str, margin: float = 0.0) -> tuple[str, ...]: ...
        # Ids whose bounds overlap object_id's bounds expanded by margin, excluding
        # object_id itself.

    def pairs_overlapping(self, margin: float = 0.0) -> tuple[tuple[str, str], ...]: ...
        # Every unordered overlapping pair, each reported exactly once, in a
        # deterministic (canonical, low-id-first) order.

    def in_region(self, region: AABB) -> tuple[str, ...]: ...

    def neighbours_of(self, object_ids: Sequence[str], margin: float = 0.0) -> tuple[str, ...]: ...
        # The scoping primitive ADR-011 requires for validation at scale: the given
        # (changed) objects PLUS their spatial neighbours, deduplicated.

    @property
    def size(self) -> int: ...

    @property
    def stale_count(self) -> int: ...
```

## Invariants

These are what the test suite (`spatial_test.py`) checks and what any future change must
keep true:

1. **No silent staleness.** After `invalidate(id)`, the next query that touches `id` must
   reflect the object's *current* engine bounds, not whatever was cached before. A
   plausible-looking wrong answer is worse than an exception here.
2. **`nearby` excludes the subject.** An object never reports itself as its own neighbour.
3. **`margin` genuinely widens the search.** `margin=0` must not report objects that don't
   touch; a positive margin must catch near-misses that `margin=0` doesn't. If margin has
   no observable effect, every caller relying on it (broad-phase pre-filtering before a
   precise check) silently gets `margin=0` behaviour regardless of what it asked for.
4. **`pairs_overlapping` reports each pair once, in a stable order.** Neither the same
   pair in both orders nor a different iteration order between two runs of the same,
   unchanged scene.
5. **`remove` is final.** A removed id never resurfaces in `nearby`, `pairs_overlapping`,
   `in_region`, or `neighbours_of`, and `bounds_of` on it raises an error that names the
   id rather than returning stale geometry.
6. **Degenerate geometry does not crash the index.** A zero-size (point) `AABB` — a
   collapsed scale, a bad generator — must be indexable and queryable like any other
   object, not a crash that takes down proximity queries for the whole scene.
7. **Determinism.** Rebuilding the same scene twice produces identical query ordering.
   This is what lets a live-view diff distinguish "nothing changed" from "something did."
8. **Empty index is a normal state, not an error state.** Every aggregate query
   (`pairs_overlapping`, `in_region`, `neighbours_of`) on a scene with no objects yet
   returns empty rather than raising.

## What this module deliberately does not do

Per ADR-011: non-convex mesh-mesh penetration *depth* is unsolved in the general case.
`SpatialIndex` only ever answers "do these bounds overlap, and by how much along a
separating axis" — a broad-phase, AABB-level question. Precise geometric checks (actual
triangle intersection, penetration depth) are `measure`'s job, scoped down to the
candidate pairs this module returns. `spatial` never claims a defect on its own; it
narrows the search space for the module that does.

## Dependencies

- `src/contracts/` for `AABB`, `Vec3`, `Transform`, `EngineProtocol` (frozen surface —
  never edited from here; see `.pipeline/contract-requests.json` for anything missing).
- `src/testing/` (`FakeEngine`, via the root `engine` fixture) in tests only.
- No `bpy`, ever.
