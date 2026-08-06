# export — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever works on this module next.

## Status

**GREEN.** Every function here is implemented and its suite passes. This module was built test-first (Rule 4): the tests were written against the contract, run, and confirmed failing on `NotImplementedError` before any body existed.

## Commands

```bash
# this module only
pytest src/export -q

# one file
pytest src/export/conversion_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

`unit_scale_test.py` is the **only** file in this module that uses `needs_blender`, and the
only one that may. Everything else runs against `testing.FakeEngine` (or, for
`conversion.py`, no engine at all) with no Blender installed, and must stay that way — the
whole point of the module is that the decision layer tests without Blender.

The exception is load-bearing, not laziness: `unit_scale_test.py` pins the four profiles'
`metres_per_unit` constants, and the only way to prove a unit constant is to read the size
of the thing that actually landed on disk. `FakeEngine.export_gltf` records the call and
writes no file, so against the fake that test could only re-divide by the constant it is
trying to check, which proves nothing. Its two pure tests (`test_documented_*`,
`test_roblox_mass_unit_*`) carry no marker and still fail on a wrong constant with no
Blender present.

## Boundaries

- Write only inside `src/export/**`. `src/contracts/`, `src/testing/`, and `conftest.py` are
  frozen surfaces owned elsewhere (Rule 5) — read them, never edit them.
- If the contract in `src/contracts/` is missing something this module needs, do not edit
  it. File the need instead (see the main agent's contract-request process) and adapt
  locally against the current contract.
- `export/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs
  in one of the four responsibility files instead.
- Nothing outside `export/` may import `export.conversion`, `export.budget`, etc. directly —
  only `from export import <name>`, per `export/__init__.py`'s `__all__`.
- **Do not import `src/measure/` or `src/scene/`.** Both are stubbed; a call into either
  raises `NotImplementedError` and would take this module down with it. Any geometry check
  `export` needs (e.g. the structural pre-flight behind the warning banner) reads
  `EngineProtocol.snapshot()` directly, never through those modules.

## Implementation notes for whoever picks this up

- **The axis remap that keeps a Y-up target right-handed is `(x, y, z) -> (x, z, -y)`** —
  the same formula Blender's own glTF exporter uses to go from Z-up to Y-up without a
  handedness flip. Apply it whenever `profile.up_axis is UpAxis.Y`; leave the axes alone for
  `UpAxis.Z` (Unreal). `flip_x` and `negate_rotation` are separate steps applied *after*
  this remap, read straight off the fields already on `ExportProfile` — never re-derive them
  from `profile.handedness`; Unreal is left-handed with `flip_x=False`, which only makes
  sense if the two stay independent inputs.
- **`convert_quaternion` remaps the vector part `(x, y, z)` exactly like `convert_point`**,
  then negates it again (all three components) when `profile.negate_rotation` is set. `w` is
  never touched. `conversion_test.py::test_unity_flips_a_rotations_sign` isolates this from
  `flip_x` by rotating about Blender's Z axis specifically — work through why before
  assuming a different remap will also pass it.
- **`convert_scalar` is `profile.to_target_units(metres)`** — do not re-derive the division,
  `ExportProfile` already owns it (`src/contracts/export_profiles.py`).
- **`round_trip` needs the true mathematical inverse of `convert_point`**, not a second call
  to `convert_point` with a hand-picked profile. Work the algebra from the forward transform
  above rather than guessing a profile whose forward pass happens to look like the inverse.
- **`check_budget` picks exactly one threshold per call**: `profile.budgets.get(asset_class)`
  when `asset_class` is given, `profile.max_triangles_per_mesh` when it is not. Never both,
  never a minimum of the two — `budget_test.py::
  test_asset_class_selects_the_per_class_budget_instead_of_the_hard_ceiling` is the test
  that catches either mistake.
- **`export_scene` must reach every conversion field into `EngineProtocol.export_gltf`**:
  `y_up=profile.up_axis is UpAxis.Y`, `mirror_x=profile.flip_x`,
  `negate_rotation=profile.negate_rotation`, `scale=profile.to_target_units(1.0)`.
- **Defects never gate the write.** Compute them, attach them to the `ExportReport`, call
  `engine.export_gltf` regardless, return `ok=True`. `over_budget_by`/`budget` on
  `ExportReport` carry the single-mesh budget overage as a dedicated summary line (see
  `contracts/contracts_test.py::test_export_report_banner_states_what_is_wrong`); other
  defects (e.g. non-manifold edges) go in `defects`.
- Keep the one-file-per-responsibility split from `README.md`. A check that grows past the
  300-line soft cap (`.claude/rules/modularity.md`) wants a private helper module under
  `export/`, not a bigger `writer.py` or `budget.py`.

## Test layout

Mirrors the four responsibility files: `conversion_test.py`, `budget_test.py`,
`writer_test.py`, `registry_test.py`. A new profile or a new conversion edge case gets its
test added to the matching file, not a new top-level test file, unless it grows enough to
need its own responsibility split (at which point split the source file the same way first).

`unit_scale_test.py` is the one file with no source counterpart, because what it tests is
not code in this module — it is the four `metres_per_unit` numbers in
`contracts/export_profiles.py` (frozen, main-agent-owned). It exists because every other
test here reads that number from the same table the code under test reads it from, so all of
them pass for **any** value, including a wrong one. Two rules follow, and breaking either
returns the module to that state:

- **Never import `PROFILES` for the expected side of an assertion in that file.** The
  documented figures are literals in `DOCUMENTED_METRES_PER_UNIT` with the citation and the
  date checked beside them. The contract table is only ever the *measured* side.
- **Never assert on `convert_scalar`/`to_target_units` output there.** The measured side is
  decoded from the vertex positions of a `.glb` the real Blender exporter wrote. The failure
  this catches (an asset silently exported at the wrong physical size) exists on disk, so
  that is where it has to be read from.

A new export profile adds a row to `DOCUMENTED_METRES_PER_UNIT`, a citation in the module
docstring, and nothing else — both tests are parametrized over that dict's keys.
