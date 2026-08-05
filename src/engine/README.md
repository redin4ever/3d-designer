# `engine`

> **This is the only module in the entire repository permitted to `import bpy`.**
> If you are writing code anywhere else and think you need `bpy`, you don't — you need a
> method on `contracts.EngineProtocol` (real implementation here, fake at
> `src/testing/fake_engine.py`) or a contract request. See ADR-008.

## What this is

`engine` implements `contracts.EngineProtocol` (`src/contracts/engine.py`) against Blender
5.2 LTS's data API (ADR-001). It is the sole boundary between this product and Blender: every
other module — `ops`, `detail`, `export`, the MCP server — is written against the Protocol
and is handed either `BlenderEngine` (this module) or `testing.FakeEngine` at the composition
root, never bpy directly.

That split is what makes the rest of the codebase testable with no Blender installed. It is
also what survives a Blender version bump: 4.0 renamed Principled BSDF sockets, 5.0 renamed
Grease Pencil, 3.2 replaced context-override dicts with `temp_override` — none of it with a
deprecation policy. A version bump touches files in this directory and nothing else.

## Layout

```
engine/
  __init__.py            barrel — exports BlenderEngine, create_engine
  session.py              bpy lifecycle: construction, backend_name, reset()
  mesh.py                 MeshOps       — create/edit/inspect geometry
  modifiers.py             ModifierOps   — bevel, boolean, array-along-curve, repairs
  surfacing.py             MaterialOps + UVBakeOps — materials, unwrap, bake
  exporting.py             ExportOps     — glTF/GLB via Blender's own exporter
  raw.py                   RawOps        — execute() (ADR-009)
  conformance.py            barrel for the shared behavioural checks below
  conformance_*.py          one check-file per actor, same split as above
  conformance_test.py       every universal check, run against FakeEngine — no marker
  blender_test.py           every check, run against real BlenderEngine — needs_blender
```

`BlenderEngine` is `MeshOpsMixin` + `ModifierOpsMixin` + `SurfacingMixin` + `ExportingMixin`
+ `RawOpsMixin`, composed in `session.py`, which also owns what belongs to none of them:
construction, `backend_name`, `reset()`.

## The conformance suite

`FakeEngine` is the specification. Every behavioural assertion in `conformance_*.py` is
written once as a plain function taking an `engine: EngineProtocol`, then run twice:

- `conformance_test.py` — against `FakeEngine`, always, on any machine.
- `blender_test.py` — against the real `BlenderEngine`, `@pytest.mark.needs_blender`,
  skipped automatically (by the root `conftest.py`) when `bpy` is not importable.

If `BlenderEngine` disagrees with `FakeEngine` on one of these checks, every module tested
against the fake is testing a lie. A handful of checks are Blender-only (`backend_name`
format, `export_gltf`'s actual file output) because `FakeEngine` does not simulate them —
see the module docstring in `conformance.py` for exactly which, and why.

## Working here (ADR-001 constraints, verified in this environment)

- **Prefer the data API (`bpy.data`, `bmesh`) over `bpy.ops`.** Many operators `poll()`-fail
  without a window/screen/area, which in-process `bpy` never has. Where an operator is
  unavoidable, wrap it in `bpy.context.temp_override()`.
- **`bpy`-as-a-module has no `bpy.context.window` at all** — stricter than
  `blender --background`. UV bake is the operation most likely to need the subprocess
  fallback (`create_engine(prefer_subprocess=True)`, shelling out to the real
  `blender.exe`).
- **A fresh `bpy` scene is not empty.** It holds a default cube, camera and light. `reset()`
  must clear all of it, not just objects this session created — see
  `conformance_session.check_reset_leaves_zero_objects`.
- **Blender stores UV coordinates per face-corner, not per vertex.** `MeshSnapshot` requires
  exactly one UV per vertex; satisfying that across a seam may mean splitting vertices in
  `snapshot()`.
- Every method not yet implemented raises `NotImplementedError("engine.<name>: not
  implemented")`. Replace the raise with real bpy code; do not change the signature — it is
  the Protocol's, in `src/contracts/engine.py`.

## Running the tests

```
pytest src/engine -q                 # conformance_test.py always runs; blender_test.py
                                      # skips automatically without bpy
pytest src/engine -q -m needs_blender  # only the real-bpy suite
```
