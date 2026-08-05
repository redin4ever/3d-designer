# export — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions for whoever writes the bodies of the stubs here.

## Status

Currently **RED by design**. Every function in `conversion.py`, `budget.py` and `writer.py`
raises `NotImplementedError("export.<name>: not implemented")`. `registry.py` is the one
exception — `EXPORT_SPECS` is real, constructed `ToolSpec` data, not a stub, so contract
validation (`ToolSpec.__post_init__`) already runs at import time; its tests already pass.
The tests in this directory were written against the contract in `src/contracts/` and
ADR-010 before any implementation existed (Rule 4) — they are the spec. Do not change a
test to make it pass; if a test seems wrong, it is describing a real product requirement
(re-read `docs/adr/ADR-010-export-profiles-roblox-first.md` before concluding otherwise).

## Commands

```bash
# this module only
pytest src/export -q

# one file
pytest src/export/conversion_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
pytest src -q
```

No `needs_blender` marker is used anywhere in this module — everything here runs against
`testing.FakeEngine` (or, for `conversion.py`, no engine at all) with no Blender installed,
and must stay that way.

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
