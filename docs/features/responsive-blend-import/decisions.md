# Responsive model and Blender import decisions

## User decision

- **Q-01 — `.blend` behavior.** Options: append editable meshes; replace the current scene. Chosen: **append editable meshes**. User’s words: “append”.

## Recorded assumptions

- **Q-02 / A-062:** `.blend` is import-only; current export choices do not change.
- **Q-03 / A-063:** append mesh objects only and warn about skipped cameras, lights, empties, and other datablocks.
- **Q-04 / A-064:** append editable local objects and mesh data, with no source-library link.
- **Q-05 / A-065:** import every mesh object available in the Blender file once.
- **Q-06 / A-066:** AUTO treats `.blend` as Z-up; explicit axis overrides still work.
- **Q-07 / A-067:** scale and flatten options work as they do for interchange formats.
- **Q-08 / A-068:** any failure rolls back the entire import and preserves the prior scene.
- **Q-09 / A-069:** naming conflicts keep both objects using Blender’s unique-name policy.
- **Q-10 / A-070:** retain job feedback and provide a clear completion or actionable failure.
- **Q-11 / A-071:** simplification is viewport-only; authoritative Blender, save, and export geometry stays complete.
- **Q-12 / A-072:** transmitted full-scene previews cap at 40,000 triangles and remain exact below that limit; the software canvas uses a smaller adaptive draw cap.
- **Q-13 / A-073:** interaction draws at most 10,000 preview triangles; the Canvas safety cap may be lower.
- **Q-14 / A-074:** deterministic, evenly distributed triangle sampling compacts all referenced attributes.
- **Q-15 / A-075:** divide the scene budget proportionally with a fair per-mesh minimum when possible.
- **Q-16 / A-076:** preview simplification is disclosed in wire metadata and a concise viewer notice.
- **Q-17 / A-077:** rendering is invalidation-driven instead of continuous while idle.
- **Q-18 / A-078:** settled detail returns 120 ms after interaction stops.
- **Q-19 / A-079:** asynchronous texture completion explicitly requests a redraw.
- **Q-20 / A-080:** scenes under the budget render exactly as before.
- **Q-21 / A-081:** `.blend` is not offered or accepted as a model export format.
- **Q-22 / A-082:** the existing 512 MB upload safety limit remains.
- **Q-23 / A-083:** corrupt Blender files return a named error without partial mutation.
- **Q-24 / A-084:** real-browser camera input must be accepted within 150 ms in the regression fixture.
- **Q-25 / A-085:** improve the existing Canvas2D path; a WebGL rewrite is outside this fix.
