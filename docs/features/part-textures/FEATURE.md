# Part textures

Parts can now use reusable PBR texture materials from six built-in presets or imported
PNG, JPEG, and WebP maps. Materials can be created, listed, updated, and applied by agents
or from the selected-object inspector, including multi-selection, UV generation, mapping
controls, persistence, live viewport sampling, Blender nodes, and portable exports.

## How it is wired in

- Engine contract: `src/contracts/engine.py` — texture material creation and assignment.
- Blender: `src/engine/surfacing.py` and `src/engine/texture_materials.py` — image/procedural
  nodes, correct colour spaces, mapping transforms, and serialized material metadata.
- Agent tools: `src/ops/texture_materials.py`, `src/ops/registry.py`, and
  `src/mcp_server/session_specs.py` — create, update, apply, replay, and read-only listing.
- Managed assets: `src/textures/library.py` and `src/app/live.py` — validated copies,
  browser import, allowlisted serving, and reusable manifests.
- Viewer: `src/contracts/wire.py`, `src/viewer/payloads.py`, and
  `frontend/src/scene-renderer.js` — material definitions and perspective-correct UV sampling.
- Inspector: `frontend/index.html` and `frontend/src/texture-inspector.js` — preset library,
  four map channels, repeat/rotation/offset, slot override, and multi-part apply.
- Undo/export: `src/scene/geometry_snapshot.py` and `src/engine/exporting.py` — UV/material
  restoration, embedded GLB textures, and separate glTF assets.

## Decisions

See [decisions.md](decisions.md).

## Assumptions still standing

- A-020 — the initial built-in set is wood, brick, concrete, stone, metal, and plaster.
  Reversal: change the preset catalog and procedural-node mappings.
- A-021 — texture mutations are available in every editing phase. Reversal: narrow the
  roles on the three texture ToolSpecs and update the measured role counts.
- A-022 — each imported image is capped at 32 MB. Reversal: change the shared library
  limit and HTTP request budget together.

## Noticed but not done

- Built-in presets are deterministic procedural materials; they are not a bundled library
  of photogrammetry assets.

## Known gaps

- Interactive visual QA could not run in this environment: no in-app browser was available,
  and the repository's Puppeteer suite could not find its pinned Chrome binary. The full
  backend suite, all 180 frontend unit tests, and the add-feature wiring gate passed.
