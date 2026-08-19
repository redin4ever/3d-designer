# Scene file import and export — decisions

The user answered **“recommended”** on 2026-08-10, selecting the first option in every question below.

| ID | Decision | Options offered | Chosen |
|---|---|---|---|
| Q-01 | File jobs | Native projects + 3D models; models only; projects only | Native projects + 3D models |
| Q-02 | Access | Editor and AI agents; editor only; agents only | Editor and AI agents |
| Q-03 | Native project fidelity | Portable history and textures; external references | Portable history and textures |
| Q-04 | Model formats | GLB/glTF, FBX, OBJ, STL, PLY, USD; GLB/glTF only; GLB, FBX, OBJ, STL | GLB/glTF, FBX, OBJ, STL, PLY, USD |
| Q-05 | Native format | Self-contained `.forge3d`; JSON plus asset folder | Self-contained `.forge3d` |
| Q-06 | `.blend` | Exclude initially; import meshes; open as project | Exclude initially |
| Q-07 | Non-mesh data | Geometry/materials with warnings; attempt everything | Geometry/materials with warnings |
| Q-08 | UI location | Blender-style File menu; top-bar buttons; settings | Blender-style File menu |
| Q-09 | UI flow | Dedicated dialogs; immediate pickers | Dedicated dialogs |
| Q-10 | Shortcuts | Ctrl+O/S/Shift+S; menu only | Ctrl+O/S/Shift+S |
| Q-11 | Import vs Open | Import adds and Open replaces; both replace; both add | Import adds and Open replaces |
| Q-12 | Name collisions | Deterministic suffix; ask; reject | Deterministic suffix |
| Q-13 | Hierarchy | Flatten to world transforms; preserve hierarchy | Flatten to world transforms |
| Q-14 | Units/axes | Auto-normalize with override; trust source; always ask | Auto-normalize with override |
| Q-15 | Export scope | Selection else scene; whole scene; always ask | Selection else scene |
| Q-16 | Editor conversion | Generic glTF metres; Roblox; always ask | Generic glTF metres |
| Q-17 | Multi-file download | ZIP; self-contained formats only | ZIP |
| Q-18 | Completion | Auto-download plus dialog/log; Download button; dialog only | Auto-download plus dialog/log |
| Q-19 | Concurrency | Import/Open paused and export anytime; all anytime | Import/Open paused and export anytime |
| Q-20 | Undo | One import step; one per object; none | One import step |
| Q-21 | Failure | Atomic refusal; partial import | Atomic refusal |
| Q-22 | Long work | Background progress/cancel; blocking | Background progress/cancel |
| Q-23 | Project assets | Embedded; external references | Embedded |
| Q-24 | Missing dependencies | Atomic list; partial open | Atomic list |
| Q-25 | Unsaved work | Save/Discard/Cancel; replace; refuse | Save/Discard/Cancel |
| Q-26 | Legacy JSON | Open and offer resave; new package only | Open and offer resave |
| Q-27 | Agent phases | Import every phase, export Polish; Blockout only; both Polish | Import every phase, export Polish |
| Q-28 | Agent paths | Any local path; managed only | Any local path |
| Q-29 | Existing export defaults | Preserve Roblox and use generic in editor; change all | Preserve Roblox and use generic in editor |
| Q-30 | Browser limit | 512 MB; 2 GB; none | 512 MB |
| Q-31 | Remote sources | Local only; HTTPS | Local only |
| Q-32 | Managed storage | Content-addressed/deduplicated; copy per import | Content-addressed/deduplicated |

User’s verbatim response: **“recommended”**.
