# uv — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever extends the bodies here next.

## Status

**GREEN.** Every function in `seams.py`, `quality.py`, `unwrap.py`, `bake.py` and
`_uv_geom.py` is implemented and its test suite passes. `results.py` (`UVResult`,
`BakeResult`) and `specs.py` (`UV_SPECS`) were always real, constructed data, never stubs —
the same convention `src/detail/results.py` and `src/export/registry.py` use.

The tests were written against the module brief and `src/contracts/` before any
implementation existed (Rule 4) — they are the spec. Do not change a test to make it pass; if
a test seems wrong, re-read its docstring first (every test here states the product-level
consequence of the failure it guards, not just the assertion).

## Commands

```bash
# this module only
pytest src/uv -q

# one file
pytest src/uv/seams_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker is used anywhere in this module — everything here runs against
`testing.FakeEngine` with no Blender installed, and must stay that way. `src/mcp/` is a
separate, still-`"planned"` module (`.pipeline/modules.json`) with pre-existing, unrelated
`NotImplementedError` failures of its own — `pytest src -q` reporting those is not a
regression in this module; they do not reference `uv` at all (its `build_registry`/
`tools_for` stubs raise before ever looking at `UV_SPECS`).

## Boundaries

- Write only inside `src/uv/**`. `src/contracts/`, `src/testing/`, and `conftest.py` are
  frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- `uv/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs in one
  of the responsibility files instead.
- Nothing outside `uv/` may import `uv.seams`, `uv.bake`, etc. directly — only
  `from uv import <name>`, per `uv/__init__.py`'s `__all__`.
- Do not import `bpy`. `EngineProtocol` (from `contracts`) is the only engine surface this
  module is written against; the real engine's `unwrap`/`mark_seams`/`bake` are implemented
  elsewhere (`src/engine/`) and are out of scope here.
- **Do not import `src/detail/`.** `.pipeline/modules.json` lists this module's only runtime
  dependency as `contracts` (`measure` is design-time/integration-order only, per
  `README.md`'s own Dependencies section). `suggest_seams`'s dihedral-angle candidate search
  is modelled on `src/detail/edges.py`'s `select_bevel_edges` — same formula, same "exactly
  two adjacent triangles" candidate rule — but reimplemented locally in `seams.py` rather
  than imported, on purpose.

## Implementation notes for whoever picks this up next

- **`suggest_seams` applies no convexity or "hidden face" filter**, unlike
  `detail.select_bevel_edges`. A hard crease is a legitimate seam candidate regardless of
  which way it folds, and a seam that faces away from the camera is, if anything, the *best*
  place to hide a texture discontinuity — the opposite of the bevel module's reasoning for
  excluding hidden edges. Do not port that filter over without re-deriving why it would even
  apply here.
- **`compute_uv_proxies` (in `quality.py`) is the one true source for coverage/max-stretch/
  overlap-count.** Both `uv_quality()` (boxes the three numbers into `Measurement`) and
  `unwrap()` (carries them un-boxed on `UVResult`) call it — never recompute any of the three
  by a second formula in either caller, or the two will silently drift apart from each other.
- **Degenerate (near-zero-area) UV triangles are excluded from both the stretch ratio and the
  overlap scan**, not included with a sentinel "infinite" value. `FakeEngine.unwrap`'s planar
  XY projection produces exactly these for a cube's side faces (three colinear UV points, in
  every case), and their true stretch is unbounded — folding them into a "worst case" would
  make that number always report the same meaningless constant instead of the worst
  *measurable* one. `_UV_AREA_EPS` in `quality.py` is the threshold.
- **`triangles_overlap` (in `_uv_geom.py`) treats a shared edge or vertex as *not*
  overlapping**, via an `eps`-tolerant Separating Axis Theorem — a well-formed unwrap tiles
  adjacent triangles edge-to-edge, and that contact must never register as the defect this
  function exists to catch. Verified in `quality_test.py` against a single quad's two
  triangles (touch along the diagonal, zero overlap) contrasted with a cube's top/bottom
  faces (identical UV triangles under the fake's projection, genuine full overlap).
- **`bake()`'s "unwrap only if missing" check is a single `snapshot.uvs is None` read**, not
  a flag threaded through from a prior call. This is deliberate: it makes the policy
  reconstructible from engine state alone, with no hidden bookkeeping — see
  `bake_test.py::test_bake_does_not_reunwrap_an_object_that_already_has_uvs`.
- **`unwrap_and_bake`'s `**kw` splitting is a fixed, hardcoded key set** (`_UNWRAP_KEYS`,
  `_BAKE_KEYS` in `bake.py`), not `inspect`-based introspection of `unwrap`'s/`_perform_bake`'s
  signatures. An unrecognised keyword raises `TypeError` naming it rather than being silently
  dropped — a caller's typo (`resolutoin=2048`) must not vanish into a default value with no
  signal at all.
- Keep the one-file-per-responsibility split from `README.md`. A function that grows past the
  300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module under
  `uv/`, not a bigger source file.

## Test layout

Mirrors the responsibility files, plus one for the shared result types and one for the tool
registry: `results_test.py`, `seams_test.py`, `quality_test.py`, `unwrap_test.py`,
`bake_test.py`, `specs_test.py`. `uv_test.py` is the exception — it exercises the barrel's
public exports together (suggest → unwrap → quality → bake, chained the way a real caller
would), rather than one function's responsibility file at a time. A new case for one existing
function goes in its matching file; a genuinely new cross-cutting scenario goes in
`uv_test.py`.

## Assumptions on record

- **`MetricKind` has no dedicated member for coverage, max-stretch or overlap-count.**
  `uv_quality` reuses `MetricKind.VOLUME`/`DISTANCE`/`TRIANGLE_COUNT` respectively and carries
  the real name in `Measurement.detail` — the same resolution `src/detail/report.py` already
  applied to an identical gap. Do not edit `contracts.MetricKind` to add dedicated members
  (Rule 5); file the need instead if a future pass wants to.
- **Per-vertex UVs, not per-corner.** `contracts.MeshSnapshot.uvs` is one coordinate per
  vertex — inherited from the frozen contract, not a choice made in this module. See
  `README.md`'s "Known simplification" section for what this does and does not let the
  overlap detector see.
- **The out-of-range seam validation in `unwrap()` raises a plain `ValueError`**, not
  `contracts.EngineError` — this is a decision-layer input check that never reaches the
  engine at all, not an engine-reported failure, so it does not carry a `rule`/`suggestion`
  pair the way an `EngineError` would.
