# ADR-016 — The viewport is a hand-written Canvas2D renderer, not three.js

**Status:** accepted · **Date:** 2026-08-06 · **Source:** Phase 6 `drift.md` · **Supersedes:** ADR-008's renderer clause

## Decision

`frontend/src/viewport.js` and `scene-renderer.js` implement perspective projection,
quaternion orbit, depth sorting and a `requestAnimationFrame` loop directly against Canvas2D.
There is no three.js dependency and none is planned.

## Context

ADR-008 named three.js for the static frontend. It was never installed: this machine has no
network access to fetch it, and vendoring a copy was not attempted. The implementing agent
wrote a renderer instead and recorded the reason in `frontend/README.md:52-68` and in
`scene-renderer.js`'s own header — an honest, load-bearing decision that simply never made it
into an ADR.

Phase 6's drift review classified this as *deliberate drift with a recorded reason*, which is
the acceptable category. This ADR moves it into the record proper so ADR-008 stops describing
a dependency that does not exist.

## Consequences

- Gate A 5.1 and 5.3 ("live 3D view", "latest change highlighted") are met by what shipped;
  only ADR-008's technology choice drifted.
- The renderer is ours to maintain. It handles what this product produces — flat-shaded
  triangle meshes with per-object transforms — and does not handle materials, textures,
  shadows or anything else three.js would have given for free. Anything wanting those is a
  three.js migration, not an incremental change.
- No network dependency in the frontend at all, which suits a tool that runs on the user's own
  machine (Gate A 7.1) and matches the artifact-style constraint the rest of the frontend was
  built under.

## Superseded by

Nothing.
