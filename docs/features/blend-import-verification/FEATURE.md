# Blender Import Repair and Verification

Native `.blend` append now preserves the model's authored world placement, including parented meshes and linked duplicates that share mesh data.

## Root cause

`bpy.data.libraries.load` creates objects outside the active scene. The importer read `matrix_world` before linking those objects, so Blender returned identity matrices and flattening collapsed parts to the origin. When multiple objects shared one mesh datablock, applying different world transforms to that shared data also corrupted the instances together. The previous regression used one origin object and could not observe either failure.

## How it is wired in

- Native loader: `src/engine/model_io.py` links the complete loaded hierarchy into the active scene and updates Blender before capturing mesh world matrices.
- Flattening: shared mesh datablocks become single-user before per-object world transforms are baked.
- Engine regression: `src/engine/model_io_test.py` imports parented linked duplicates and checks exact baked vertex positions, identity transforms, editability, and independent data.
- Product-path regression: `src/app/scene_file_integration_test.py` uploads real `.blend` bytes through the background job/owner-thread boundary, checks authoritative geometry and the opaque scene operation, and proves a viewport mesh message is produced.

## Decisions and assumptions

See [decisions.md](decisions.md) and [assumptions.md](assumptions.md). The browser/API request, append semantics, atomic rollback, mesh-only scope, progress surface, and viewer translation remain unchanged.

## Verification

- The two new regressions failed against the old importer for lost placement and shared data, then passed after the repair.
- 16 targeted engine and application integration tests passed with real Blender.
- The complete backend and deterministic agent-eval suite passed.
- All five checked-in native assets imported successfully: 759 meshes and 1,410,096 triangles total; per-file measured results are retained in the run output.

## Noticed but not done

Applying Blender modifiers during import remains separate policy scope. This repair preserves the existing editable mesh/modifier behavior.

## Known gaps

None for the reproduced transform and shared-instance failures.
