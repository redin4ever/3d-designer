# gaps — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions, and the reasoning behind the non-obvious choices, for
whoever picks this up next.

## Status

**GREEN.** Written test-first against the contract in `src/contracts/` and the detectors
in `src/measure/` (Rule 4): every function in this package started as a
`NotImplementedError("gaps.<name>: not implemented")` stub, `gaps_test.py` was run and
confirmed to fail on that error (not `ImportError`) for every test but the `GAPS_SPECS`
one, and only then was each function implemented. `registry.py` (`GAPS_SPECS`) was real
from the start, the same way `constraints.AnchorResolution` and `export.EXPORT_SPECS` are
— constructing a `ToolSpec` runs `contracts.ToolSpec.__post_init__`'s own validation, and
that must run (and pass) whether or not the handler behind it exists yet.

## Commands

```bash
# this module only
pytest src/gaps -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker is used anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way.

## Boundaries

- Write only inside `src/gaps/**`. `src/contracts/`, `src/measure/`, `src/testing/`, and
  `conftest.py` are frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- `gaps/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs in
  one of the responsibility files instead.
- Nothing outside `gaps/` may import `gaps.rebuild`, `gaps.tiered`, etc. directly — only
  `from gaps import <name>`, per `gaps/__init__.py`'s `__all__`.
- **Detection is `measure`'s job, never re-derived here.** Every repair calls the matching
  `measure.find_*` function both to decide whether there is anything to do and to verify
  the fix afterwards. The one partial exception is documented below
  (`_flagged_triangles`) — it parses a detector's *output*, it does not recompute the
  detector's *algorithm*.

## Why some repairs call an engine primitive and some rebuild from a snapshot

`fill_boundary_holes`, `weld_duplicates` and `merge_shells` (`primitives.py`) are one-line
wrappers over `ModifierOps.fill_holes` / `ModifierOps.merge_by_distance` — the engine
already does exactly this, so gaps does not re-derive it.

`remove_loose`, `fix_normals` and `split_non_manifold` (`rebuild.py`) have no matching
primitive — there is no "delete this one loose vertex" or "flip this one face" method on
`EngineProtocol`, and `src/contracts/` cannot be edited to add one (frozen surface, Rule
5; a genuine gap would be filed as a contract request, not patched around). Where a fix is
still possible, these instead: read `engine.snapshot`, compute the corrected
vertex/triangle arrays in plain Python (the same kind of pure computation `measure` already
does over a snapshot), and push the result back through `engine.delete` +
`engine.create_mesh` — the one primitive general enough to realise an arbitrary geometry
change. This is composition of two real primitives, not a second mesh-editing backend, and
it is why `_rebuild` in `rebuild.py` deletes before recreating: `create_mesh` on a live id
mints `object_id.001` instead of overwriting it (`FakeEngine._unique`), which would change
the object's identity out from under the caller.

**Known side effect:** rebuilding always flattens n-gon faces to their triangulation.
`MeshSnapshot` carries triangles only, never the original polygon structure, so there is no
n-gon shape left to rebuild with. Acceptable for a repair pass; worth knowing if a caller
compares `polygon_count` before and after.

## `fix_normals` and why it cannot use `recalculate_normals`

`ModifierOps.recalculate_normals(object_id, inside=False)` looks like the obvious tool,
and it is deliberately not used. In `FakeEngine` (and, by the ADR-005/008 boundary, in
intent for the real engine too) it only ever flips **every** face — fully, if
`inside=True`, or not at all if `inside=False`. `measure.find_flipped_normals` flags a face
based on whether its winding *disagrees with its neighbours*, a purely relative signal that
is invariant under flipping every face at once. Reversing everything changes the mesh's
overall inside/outside orientation but leaves the exact same face(s) disagreeing with their
neighbours — it cannot fix a single reversed face among many correct ones.

The fix instead has to reverse *exactly* the flagged triangles, and `contracts.Defect`
carries no structured "which triangles" field — only a human-readable `detail` string
(`contracts` is frozen; this would be a contract request, not a local patch). `_rebuild`'s
`_flagged_triangles` in `rebuild.py` parses the `"triangle(s) [i, j, …]"` substring
`measure.topology.find_flipped_normals` writes. This is fragile by construction and is
called out as such in the docstring: if that string's format ever changes, parsing returns
no indices and `fix_normals` reports the defect as unfixed (`skipped`, with a reason) —
it never silently does nothing while claiming success.

## `split_non_manifold` is a documented partial capability, not a bug

A real fix for `NON_MANIFOLD_VERTEX` — duplicate the pinch vertex, one copy per fan — was
prototyped against a snapshot rebuild (the same pattern `remove_loose`/`fix_normals` use)
and rejected. The two vertices it produces are genuinely coincident in space, by design
(that is what "the same point, now split into two" means), and
`measure.find_loose_or_duplicate` has no way to know they were split on purpose — it
immediately re-flags the new vertex as an unwelded duplicate of the old one. The "fix"
would trade one defect for a different one rather than resolving anything, which is worse
than doing nothing (`README.md`'s clean-mesh invariant). `NON_MANIFOLD_EDGE` ("split the
fan") is not even well-defined without an arbitrary rule for which two of the 3+ incident
faces keep the original edge.

`split_non_manifold` therefore only detects (via `measure.find_non_manifold_edges` +
`find_non_manifold_vertices`) and reports an honest `skipped` count with a reason — never a
false `fixed`. `repair()`'s non-manifold tier inherits this honesty for free, because it
re-measures every tier's outcome rather than trusting what was attempted.

## `close_visual_gap` needs a vector `measure` does not expose

`measure.gap_width` returns a scalar magnitude — enough to detect and verify a visual gap,
not enough to know *which way* to move an object to close one. `visual_gap.py`'s private
`_gap_vector` computes the same per-axis AABB gap `measure`'s own (private,
non-importable) `_geom.aabb_gap_vector` computes, independently — `measure`'s private
files are not importable from outside `measure/` (`measure/CLAUDE.md`), and this is a
repair-side need (the correction vector), not a re-derivation of detection. `a` is the
object that moves; `b` never does. That is an arbitrary but documented choice — nothing in
the contract prefers one side over the other.

## Test layout

One file: `gaps_test.py`, mirroring `contracts_test.py`'s single-file convention rather
than `measure`'s four-file split — this package's eight functions are short enough that
one file covers all of them under the 450-line test budget (`.claude/rules/modularity.md`)
without needing a responsibility split on the test side. If a future addition pushes it
over budget, split along the same seams `primitives.py` / `rebuild.py` / `visual_gap.py` /
`tiered.py` already draw.

## Open contract requests

- `contracts.Defect` has no structured field for which triangle/vertex indices a defect
  covers. `fix_normals` works around this by parsing `detail` text (see above); a typed
  `indices: tuple[int, ...] = ()` field would remove that fragility for any future
  index-targeted repair, not just this one.
- `EngineProtocol` (`ModifierOps`) has no primitive for deleting unreferenced vertices,
  reversing a named subset of faces, or splitting a non-manifold vertex/edge. All three
  are worked around here by rebuilding through `create_mesh`; a real engine backend would
  do this far more cheaply with a native "delete loose" / targeted flip / vertex-split
  operator, which this module cannot reach without one of these being added to the
  protocol.
