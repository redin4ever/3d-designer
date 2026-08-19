# Responsive model import and native Blender append

Forge3D can import `.blend` files as editable mesh objects without replacing the open
project, and semi-complex imports remain navigable through bounded, event-driven previews.

## How it is wired in

- Import picker: `frontend/src/file-io.js` exposes `.blend` only for model import.
- Format contract: `src/contracts/engine.py` separates import and export suffixes.
- Native loader: `src/engine/model_io.py` appends local Blender-library objects atomically,
  links mesh objects into the current scene, and removes skipped non-mesh datablocks.
- Operation boundary: `src/importing/operations.py` accepts `.blend`; export validation in
  `src/app/file_operations.py` remains interchange-only.
- Preview boundary: `src/viewer/payloads.py` deterministically compacts preview triangles;
  `src/viewer/translate.py` fairly shares a 40,000-triangle message budget and reports quality.
- Browser ingestion: `frontend/src/viewport.js` avoids re-copying typed buffers.
- Renderer: `frontend/src/scene-renderer.js` redraws only after invalidation and uses a bounded
  native Canvas2D wireframe for dense scenes rather than blocking on the software rasterizer.
- Browser proof: `frontend/tests-browser/performance.browser.mjs` paints a 1,568-triangle
  preview, checks the simplification notice, and enforces the 150 ms camera-input threshold.

## Decisions

See [decisions.md](decisions.md). The user’s explicit decision was to append rather than
replace the current scene.

## Assumptions still standing

- A-062–A-070 and A-081–A-083 define native-import scope, atomicity, naming, feedback,
  import-only behavior, upload size, and corrupt-file handling.
- A-071–A-080 and A-084–A-085 define preview-only simplification, budgets, disclosure,
  invalidation scheduling, responsiveness, and the decision not to replace Canvas2D.
- Reversal costs are recorded beside each item in `docs/ASSUMPTIONS.md`.

## Noticed but not done

- A GPU renderer could retain more shaded triangles and accurate picking on very dense scenes.
  It is a separate renderer-platform project; this feature keeps the existing Canvas2D API.
- `.blend` export is intentionally not model export. Native project persistence remains the
  `.forge3d` save path; a future “Save As Blender” flow would need separate lifecycle rules.

## Known gaps

None. Dense wireframe preview intentionally favors responsive orbit/zoom over material-accurate
picking; the authoritative editable Blender geometry, project saves, and exports remain complete.

## Verification finding

The full backend suite exposed an older `FakeEngine` regression test that deliberately rejected
`.blend`. Its expectation was updated to preserve what it was actually protecting—unsupported
formats still fail atomically—while adding explicit fake-engine parity for native Blender import.
