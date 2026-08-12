# Architectural quality

House-scale builds now use semantic operations for the relationships that previously
forced an agent to guess raw geometry:

- `add_gable_roof` builds two closed pitch-derived panels, a ridge cap, front/back rake
  trim and both eave fascias. Each rake is one continuous mitered shell; its apex meets a
  flush, overlapping ridge cap instead of two disconnected boards stopping short. Rakes
  and fascias are cut from one shared six-corner ring layout, so each pair meets across an
  exact compound-miter face with no connector blocks or fragile point contacts. Its
  `origin` is the footprint centre at the wall-top bearing plane; `width` is the gable span
  and `depth` is the ridge length.
- `add_staircase_to_landing` reads a live porch/deck/floor, derives the approach direction,
  run and rise from its bounds, and builds thin treads on two side stringers. The legacy
  `add_staircase` remains unchanged for callers that intentionally provide raw run math.
- `add_chimney` builds the masonry shaft, tapered roof flashing, overhanging crown, and
  one to four rimmed flues as predictable parts. It refuses a flue layout that cannot fit
  before creating any geometry; agents should use it instead of stretching a cube.
- `add_railing` now sweeps the top rail as one closed shell. Every slope, landing, or plan
  corner shares a true miter ring, so hidden end caps cannot intersect and no joint can
  separate after beveling.

Both tools reject impossible input before creating geometry. Their MCP operations persist
re-runnable acceptance: roof panels, ridge cap and every trim corner must meet, and the
highest tread must meet the named landing. Ridge cover and stair support intersections are
persisted as explicit joinery,
never inferred from overlap. Phase promotion evaluates these active operation checks beside
the generic scene checks and ignores undone operations.

## Agent workflow

1. In blockout, build the slab and walls, then call `add_gable_roof` and `add_chimney`.
   Do not approximate either assembly with transformed cubes.
2. In refine, cut openings, create the porch/landing, then call
   `add_staircase_to_landing`. Add railings separately so their path and spacing remain
   independently editable.
3. Read the operation report and phase acceptance results. Repair every named failure;
   there is no success-by-self-report or promotion override.
4. Continue through detail and polish for frames, trim, materials, bevels, UVs and export.
   Geometry acceptance covers measurable correctness; appearance still requires visual
   review, as specified by ADR-005.

## Compatibility and proof

The architectural additions are normal typed operations in `OPS`/`OP_SPECS`; saved operations use the
existing scene schema. Existing staircase behavior is preserved. Fake-engine geometry,
normal app composition, MCP persistence, phase gating and a real-Blender smoke test cover
the complete path. The demonstration artifacts are `artifacts/architectural_house.blend`
and `artifacts/architectural_house.png`.
