# spatial — local conventions

## Run the tests

```
python -m pytest src/spatial
```

No markers, no `bpy`, no fixtures beyond the root `engine` fixture (`conftest.py` at the
repo root — do not redefine it here). Should complete in well under a second; if it
doesn't, something is doing engine-wide work it shouldn't.

## Ownership

`src/spatial/**` only, per `.pipeline/modules.json`. This module depends on `contracts`
and nothing else in `src/`. Do not import from `measure`, `constraints`, `ops`, or any
sibling module — `spatial` is a leaf that other modules depend on, never the reverse.

## Conventions specific to this module

- **`__init__.py` is a barrel only.** All logic lives in `index.py` (and, once it grows
  past the file-size budget, in additional same-directory files re-exported from
  `__init__.py`). If `SpatialIndex` needs to split — e.g. the tree structure separated
  from the query surface — split along that seam and keep `__init__.py`'s re-export list
  unchanged; nothing outside this directory should notice.
- **Test the public interface only** (`.claude/rules/testing.md`). No test may assert on
  how the BVH is structured internally (node layout, tree depth, split heuristic) — only
  on what `SpatialIndex`'s methods return. That is what keeps the internal structure free
  to change later without touching the test suite.
- **Bounds always come from the engine.** Never hand-roll a bounding box in this module;
  read it via `engine.world_bounds(object_id)` (or `engine.snapshot(object_id).world_bounds()`
  if more of the snapshot is needed) so this module and the engine's own notion of an
  object's bounds cannot drift apart.
- **`AABB` construction can raise.** `contracts.AABB.__post_init__` rejects an inverted
  box. Do not catch and paper over that here — an inverted box is a real defect upstream
  and should surface, not be silently coerced.
- **No timing assertions.** The scale test in `spatial_test.py` checks *correctness* at
  ~500 objects via a brute-force oracle, not speed. Do not add a benchmark assertion to
  this suite; if performance needs a floor, that belongs in a separate, explicitly-marked
  benchmark, not in the unit suite that runs on every commit.

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/contracts/contracts_test.py` and `src/testing/fake_engine_test.py`:
dataclasses over dicts, `from __future__ import annotations`, and a docstring on every
test stating the product-level consequence of the test failing — not just what it checks.
