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
  conformance_mesh.py        conformance_modifiers.py    conformance_boolean.py
  conformance_shape.py       conformance_surfacing.py    conformance_materials.py
  conformance_exporting.py   conformance_raw.py          conformance_session.py
  conformance_validation.py  one check-file per actor (or, for conformance_boolean.py,
                              conformance_shape.py, conformance_materials.py and
                              conformance_validation.py, per a concern with no actor file
                              of its own — see conformance.py's docstring)
  conformance_test.py       every universal + fake-only check, against FakeEngine — no marker
  blender_test.py           every universal + Blender-only check, against real BlenderEngine
                             — needs_blender
```

`BlenderEngine` is `MeshOpsMixin` + `ModifierOpsMixin` + `SurfacingMixin` + `ExportingMixin`
+ `RawOpsMixin`, composed in `session.py`, which also owns what belongs to none of them:
construction, `backend_name`, `reset()`.

## The conformance suite

`FakeEngine` is the specification. Every behavioural assertion in `conformance_*.py` is
written once as a plain function taking an `engine: EngineProtocol`, then run against one or
both engines depending on which of three registries in `conformance.py` it belongs to:

- `UNIVERSAL_CHECKS` — run from both `conformance_test.py` (against `FakeEngine`, always, on
  any machine) and `blender_test.py` (against the real `BlenderEngine`,
  `@pytest.mark.needs_blender`, skipped automatically by the root `conftest.py` when `bpy`
  is not importable).
- `BLENDER_ONLY_CHECKS` — run only from `blender_test.py`. `FakeEngine` does not simulate
  the behaviour faithfully enough for the check to mean anything against it (e.g.
  `backend_name` format, `export_gltf`'s actual file output, a real CSG solver's exact
  bounds on `boolean`'s `difference`/`intersect` modes, `bevel_edges` actually moving the
  selected edge's vertices — `FakeEngine`'s bevel only inflates a face count).
- `FAKE_ONLY_CHECKS` — run only from `conformance_test.py`. The check depends on something
  only `FakeEngine` has: `.calls` introspection, a test-only accessor, or the root
  conftest's `engine_without_bake` fixture.

If `BlenderEngine` disagrees with `FakeEngine` on a universal check, every module tested
against the fake is testing a lie. See the module docstring in `conformance.py` for exactly
which checks are in each of the other two registries, and why.

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
  `conformance_session.check_reset_leaves_zero_objects` and, more pointedly,
  `check_reset_clears_the_live_bpy_scene`, which reads `bpy.data.objects` directly rather
  than through `list_objects()` so a private Python-side ledger cannot fake its way past it.
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
