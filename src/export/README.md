# export

Converts at the boundary. Nothing upstream of `export` knows about engine conventions
(ADR-010) — geometry inside the boundary is always Blender-native Z-up, right-handed,
metres (`src/contracts/geometry.py`). This module is the one place the Blender ->
glTF -> {Roblox, Unity, Unreal, Godot} axis, handedness and unit chain is reasoned about,
and the one place a mirror or a rotation-sign inversion can be caught before an
export -> import round trip discovers it in a different tool than the one that produced it.

## Public interface

Everything importable from `export` is declared in `export/__init__.py`. Nothing else is
public; do not import `export.conversion`, `export.budget`, etc. directly from outside this
package.

```python
# conversion — pure functions, no engine, no bpy
convert_point(p: Vec3, profile: ExportProfile) -> Vec3
convert_quaternion(q: Quat, profile: ExportProfile) -> Quat
convert_scalar(metres: float, profile: ExportProfile) -> float
round_trip(p: Vec3, profile: ExportProfile) -> Vec3        # convert then invert; == p

# budget
check_budget(engine, object_ids, profile, asset_class=None) -> tuple[Defect, ...]

# writer
export_scene(engine, object_ids, path, *, profile_name="roblox",
             asset_class=None, force=False) -> ExportReport
banner_for(report: ExportReport) -> str

# registry
EXPORT_SPECS: tuple[ToolSpec, ...]      # roles=(ToolRole.EXPORT,)
```

## The four profiles

| Profile | Up | Handedness | Unit | Conversion |
|---|---|---|---|---|
| **Roblox** (primary) | Y | right | stud (0.28 m) | axis remap only |
| Unity | Y | **left** | m | axis remap + X mirror + rotation-sign flip |
| Unreal | Z | **left** | cm | scale only, no axis remap |
| Godot | Y | right | m | axis remap only, closest to glTF |

All four unit figures are **verified against the engines' own documentation** (F-016) and
pinned by `unit_scale_test.py`, which carries the URLs and the date each was checked. The
Roblox stud is 28 cm per Roblox's unit table — a length unit, not the visual stud spacing on
a part's surface — and Roblox's documented mass unit (1 RMU = 21.952 kg = 0.28³ × 1000)
only agrees with the length row at 0.28. Do not change any of these four numbers without
re-reading that file first.

The actual numbers live in `src/contracts/export_profiles.py` (`PROFILES`) — this module
never hardcodes one; every conversion reads them off the `ExportProfile` it is given.

## Layout

One file per responsibility, so two agents extending different checks never touch the same
file:

| File | Owns |
|---|---|
| `conversion.py` | The pure axis/handedness/unit maths — `convert_point`, `convert_quaternion`, `convert_scalar`, `round_trip` |
| `budget.py` | `check_budget` — triangle counts against a profile's hard ceiling or per-class budget |
| `writer.py` | `export_scene`, `banner_for` — the actual `EngineProtocol.export_gltf` call and the `ExportReport` it produces |
| `registry.py` | `EXPORT_SPECS` — the MCP tool declarations for the export role |

## Invariants

- **Conversion is pure.** `conversion.py` takes no `engine` argument and calls nothing on
  one — this is what makes the round-trip fixture runnable with no Blender installed, and
  what ADR-010 means by "one audited conversion function per profile."
- **A round trip must recover the original point, within `contracts.EPSILON`, for every
  profile.** Tested against asymmetric points (`x != y != z`, at least one negative) — a
  symmetric point would pass even with two axes silently swapped, proving nothing.
- **Unity needs both `mirror_x` and `negate_rotation`.** Mirroring position alone leaves
  every rotation inverted — a positive rotation is clockwise in a left-handed system,
  counter-clockwise in a right-handed one. Getting one without the other is the exact
  silent round-trip bug ADR-010 exists to close, and it is invisible until the model is
  re-opened in Unity.
- **Export never blocks on a defect.** Gate A 6.3: the user chose a warning banner, never a
  block. `export_scene` always writes the file and returns `ok=True` once the named objects
  exist and the engine call succeeds; every defect found travels in the returned
  `ExportReport` instead. `force`/`ExportReport.forced` record a knowing override — they
  never gate whether the file is written.
- **`export_scene` calls `EngineProtocol.export_gltf` with every conversion field the
  profile carries** — `y_up`, `mirror_x`, `negate_rotation`, `scale` — never just `y_up`.
  `src/contracts/engine.py` documents why: an earlier draft exposed only `y_up`, which left
  the two fields a left-handed target needs together unreachable.
- **Budgets are checked, never enforced, by this module.** `check_budget` reports a
  `BUDGET_EXCEEDED` defect; deciding what to do about it is the caller's call, or a human
  reading the banner. The one exception is *severity*, not enforcement: Roblox's
  `max_triangles_per_mesh` is a platform fact — it fails import outright — so a defect from
  crossing it is not softened to look like a style preference.
- **No dependency on `src/measure/` or `src/scene/`.** Both are stubbed elsewhere in this
  tree; `export` reads geometry directly off `EngineProtocol.snapshot()` for anything it
  needs to check (e.g. the structural pre-flight behind the warning banner), never through
  those modules.

## Dependencies

`contracts` only, plus the `EngineProtocol` surface for `check_budget` and `export_scene`.
`conversion.py` has no dependency on either `contracts.engine` or an `engine` instance —
it is plain functions over plain data.

## Testing

`pytest src/export` from the repo root. Every test that needs geometry takes the shared
`engine` fixture (`conftest.py`) — a `FakeEngine`, no Blender required. `conversion_test.py`
needs no fixture at all: it is plain functions over plain data. See `CLAUDE.md` for the
exact commands and the local test-file layout.
