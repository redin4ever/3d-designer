# Responsive native model import assumptions

## A-062 — Blender files are import-only

- **Feature:** responsive-blend-import
- **Assumed:** `.blend` joins the import formats but not the export formats.
- **Blast radius / reversal:** format contracts and pickers; add a separately tested native-save flow to reverse.

## A-063 — Native import keeps mesh objects only

- **Feature:** responsive-blend-import
- **Assumed:** cameras, lights, empties and other non-mesh datablocks are skipped with a warning.
- **Blast radius / reversal:** Blender library selection; extend the scene contract before importing other types.

## A-064 — Appended objects are editable local copies

- **Feature:** responsive-blend-import
- **Assumed:** imported objects and mesh data do not remain linked to the source library.
- **Blast radius / reversal:** native import ownership; add an explicit linked-import mode to reverse.

## A-065 — Import all file meshes once

- **Feature:** responsive-blend-import
- **Assumed:** every mesh object available in the file is appended once, across its collections/scenes.
- **Blast radius / reversal:** object selection; add a pre-import object picker to narrow it.

## A-066 — Blender AUTO orientation is Z-up

- **Feature:** responsive-blend-import
- **Assumed:** AUTO applies no axis rotation to `.blend`; explicit overrides still apply.
- **Blast radius / reversal:** post-import transforms; change only the `.blend` axis policy.

## A-067 — Native imports share scale and flatten controls

- **Feature:** responsive-blend-import
- **Assumed:** unit scale and flatten behave consistently for native and interchange imports.
- **Blast radius / reversal:** import transforms; disable those controls specifically for `.blend`.

## A-068 — Native import is atomic

- **Feature:** responsive-blend-import
- **Assumed:** any failure removes all objects/data created by that import and preserves the prior scene.
- **Blast radius / reversal:** transaction cleanup; partial import would require explicit user-facing recovery.

## A-069 — Blender resolves naming conflicts

- **Feature:** responsive-blend-import
- **Assumed:** existing and appended objects are both kept using Blender’s unique-name policy.
- **Blast radius / reversal:** names and references; add a conflict dialog or prefix option.

## A-070 — Existing file-job feedback remains the progress surface

- **Feature:** responsive-blend-import
- **Assumed:** current start/completion feedback is sufficient if failures become actionable.
- **Blast radius / reversal:** import UI; add staged native-load progress events later.

## A-071 — Preview simplification never changes source geometry

- **Feature:** responsive-blend-import
- **Assumed:** only viewer payloads are reduced; Blender state, project saves and exports stay exact.
- **Blast radius / reversal:** viewer translation only; disable the preview budget to reverse.

## A-072 — Settled preview budget is 40,000 triangles

- **Feature:** responsive-blend-import
- **Assumed:** transmitted scenes below this remain exact and larger scenes use a deterministic proxy; dense scenes draw 500 distributed triangles through Canvas2D's native wireframe rasterizer.
- **Blast radius / reversal:** viewer bandwidth/detail; tune the payload and raster budget constants independently.

## A-073 — Interaction budget is 10,000 triangles

- **Feature:** responsive-blend-import
- **Assumed:** orbit and zoom draw at most 10,000 already-received preview triangles, subject to the lower Canvas2D safety cap.
- **Blast radius / reversal:** interactive visual detail; tune or disable the draw budget.

## A-074 — Preview sampling is deterministic and distributed

- **Feature:** responsive-blend-import
- **Assumed:** evenly spaced triangle selection and compact attribute remapping is adequate for navigation.
- **Blast radius / reversal:** preview silhouette; substitute a tested geometric decimator.

## A-075 — Scene budgets preserve object visibility fairly

- **Feature:** responsive-blend-import
- **Assumed:** proportional allocation with a small fair share prevents small parts disappearing.
- **Blast radius / reversal:** multi-object previews; replace the allocator policy.

## A-076 — Simplification is visibly disclosed

- **Feature:** responsive-blend-import
- **Assumed:** wire metadata and a concise viewer notice distinguish preview quality from source quality.
- **Blast radius / reversal:** protocol and status UI; hide only if another persistent indicator replaces it.

## A-077 — The viewport redraws on invalidation

- **Feature:** responsive-blend-import
- **Assumed:** scene/camera/selection/size/theme/texture changes cover every reason to redraw.
- **Blast radius / reversal:** renderer lifecycle; restore a bounded loop if an uncovered animation is added.

## A-078 — Interaction settles after 120 ms

- **Feature:** responsive-blend-import
- **Assumed:** this delay balances fluid input with fast restoration of preview detail.
- **Blast radius / reversal:** orbit/zoom feel; tune one timing constant.

## A-079 — Texture loads explicitly invalidate

- **Feature:** responsive-blend-import
- **Assumed:** asynchronous texture success/failure schedules a redraw in an otherwise idle renderer.
- **Blast radius / reversal:** material refresh; centralize invalidation if more async assets are added.

## A-080 — Small scenes remain exact

- **Feature:** responsive-blend-import
- **Assumed:** no payload or draw sampling occurs below the relevant budget.
- **Blast radius / reversal:** established viewport fidelity; lowering budgets would deliberately change it.

## A-081 — Model export does not write `.blend`

- **Feature:** responsive-blend-import
- **Assumed:** project save remains the native persistence path; model export remains interchange-only.
- **Blast radius / reversal:** export validation and picker; add a distinct Save As Blender feature.

## A-082 — Upload limit remains 512 MB

- **Feature:** responsive-blend-import
- **Assumed:** native files use the existing upload safety ceiling.
- **Blast radius / reversal:** browser and server upload validation; revise both limits together.

## A-083 — Corrupt native files fail clearly and atomically

- **Feature:** responsive-blend-import
- **Assumed:** errors name the source and leave no imported residue.
- **Blast radius / reversal:** error messages and rollback; partial recovery requires a new UX.

## A-084 — Camera input acceptance target is 150 ms

- **Feature:** responsive-blend-import
- **Assumed:** the real-browser semi-complex fixture must process navigation input within 150 ms.
- **Blast radius / reversal:** browser regression threshold; calibrate with measured supported hardware.

## A-085 — No renderer-platform rewrite

- **Feature:** responsive-blend-import
- **Assumed:** optimize current Canvas2D scheduling and work budgets; WebGL is separate scope.
- **Blast radius / reversal:** frontend renderer internals; a later renderer can retain the same scene API.
