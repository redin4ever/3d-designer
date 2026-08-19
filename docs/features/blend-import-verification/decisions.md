# Blender Import Repair — decisions

The user required `.blend` import to work as intended and to be verified. Reproduction showed that a normal Blender library object reports an identity `matrix_world` until it joins the active scene; flattening then erased authored placement. Shared mesh datablocks introduced a second corruption path when distinct transforms were baked into the same data.

| Decision | Chosen behavior | Basis |
|---|---|---|
| Q-01 | Preserve authored placement and prove the real import path. | User request. |
| Q-02–Q-04 | Evaluate after scene linking, bake exact world transforms, and make shared data single-user. | Direct reproduction of the failure. |
| Q-05–Q-08 | Continue appending editable local meshes without replacing existing geometry. | Existing product contract; no widening. |
| Q-09–Q-13 | Flatten exactly once, preserve unflattened world placement, apply conversion afterward, retain materials, and leave modifiers unchanged. | Narrow geometry correction. |
| Q-14–Q-18 | Preserve warnings, atomic rollback, browser headers, progress, pause behavior, and owner-thread execution. | Existing working boundaries. |
| Q-19–Q-20 | Verify uploaded bytes through scene/viewer, then smoke-import every repository `.blend` asset. | User asked for verification rather than a unit-only claim. |

Decision coverage: Q-01, Q-02, Q-03, Q-04, Q-05, Q-06, Q-07, Q-08, Q-09, Q-10, Q-11, Q-12, Q-13, Q-14, Q-15, Q-16, Q-17, Q-18, Q-19, Q-20.
