# Scene file import and export

forge3d now has a Blender-style **File** menu for editable project packages and ordinary
3D interchange files. Project saves are portable `.forge3d` ZIP packages containing the
operation log, current geometry, undo-barrier snapshots, imported sources, texture maps,
and content-addressed deduplication metadata.

## Editor workflow

- **Open Project** replaces the current project in place, preserving the connected browser
  and agent session. Legacy forge3d JSON documents open with a resave recommendation.
- **Save Project** and **Save As** download a self-contained `.forge3d` package.
- **Import Model** adds GLB/glTF, FBX, OBJ, STL, PLY, USD, USDA, or USDC mesh geometry as one
  opaque undo step. Advanced controls set source-up axis, unit scale, and hierarchy flattening.
- **Export Model** exports the current selection, or the whole scene when nothing is selected,
  using generic metres by default or a named target profile. Separate glTF output is bundled
  as ZIP; single-file formats download directly.
- `Ctrl+O`, `Ctrl+S`, and `Ctrl+Shift+S` open the matching flows. Import and Open require the
  run to be paused; export remains available while the run is active.

Uploads are local-only and capped at 512 MiB. Work runs through cancellable background jobs,
reports progress in the dialog, records completion/errors in the action log, and uses opaque
download tokens confined to managed temporary storage.

## Agent workflow

Agents can call `import_model_file` with any existing local model path under the repository's
existing unrestricted-local trust policy. Import is visible during Blockout, Refine, Detail,
and Polish, enters shared history, and restores from geometry snapshots across undo/redo.
The established agent export tool remains Polish-only and Roblox-compatible by default.

## How it is wired

- Contracts and engines: `src/contracts/engine.py`, `src/engine/model_io.py`, and
  `src/testing/fake_surfacing.py` define and implement the model-file boundary.
- Portable projects: `src/scene_files/package.py` validates, packs, deduplicates, and prepares
  packages without mutating the live engine; `src/scene/persistence.py` commits them in place.
- Shared history: `src/importing/operations.py`, `src/app/handlers.py`, and
  `src/mcp_server/registry.py` make imports replay-honest and agent-visible.
- Live service: `src/app/file_api.py`, `src/app/file_operations.py`, and `src/app/live.py`
  provide bounded jobs, uploads, downloads, cancellation, and application callbacks.
- Editor: `frontend/src/file-io.js`, `frontend/src/file-io.css`, and `frontend/index.html`
  provide the menu, dialogs, shortcuts, progress, selection scope, and downloads.

## Decisions

See [decisions.md](decisions.md).

## Known limits

- Native Blender `.blend` files are intentionally not part of this first interchange set.
- Browser import accepts one primary local model file. Prefer GLB or embedded glTF when a
  model would otherwise depend on external `.bin` or texture sidecars; `.forge3d` project
  packages remain fully self-contained.
