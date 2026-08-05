# detail

The answer to the user's stated deal-breaker (Gate A 1.3, verbatim: *"Still looks like glued
boxes."*). Four realism passes named at Gate A 8.4 — heuristic edge treatment, surface detail
(panel lines, greebles), material realism (varied roughness, no pure black/white albedo) — plus
a report of computable proxies for what "realistic" can actually mean as a number.

Edge treatment is the highest-leverage single lever the research turned up: a perfectly sharp
CAD edge produces a hard, artificial specular break; even a tiny bevel produces the highlight
line a viewer reads as real material. But the same research warns that bevelling *uniformly* is
itself a tell (`docs/decisions/gate-A.md`, wave 8.3) — so this module's job is never "bevel
everything", it is "bevel only what would plausibly catch light".

## Public interface

Everything importable from `detail` is declared in `detail/__init__.py`. Nothing else is
public; do not import `detail.edges`, `detail.surface`, etc. directly from outside this package.

```python
@dataclass(frozen=True)
class EdgeSelection:
    edge_indices: tuple[int, ...]   # indices into MeshSnapshot.edges()
    reasons: tuple[str, ...]        # parallel to edge_indices
    rejected: int                   # candidates considered and skipped

@dataclass(frozen=True)
class DetailResult:
    object_id: str                  # object id, or material id for vary_roughness
    changed: bool                   # False means a genuine no-op, not quiet failure
    triangles_before: int
    triangles_after: int
    detail: str = ""

# edge treatment
select_bevel_edges(snapshot, *, min_dihedral_deg=30.0, convex_only=True,
                    exclude_hidden=True) -> EdgeSelection
bevel_width_for(snapshot, *, fraction=0.004, minimum=0.0005, maximum=0.01) -> float
apply_edge_treatment(engine, object_id, *, segments=2, min_dihedral_deg=30.0,
                      convex_only=True, exclude_hidden=True, fraction=0.004,
                      minimum=0.0005, maximum=0.01) -> DetailResult

# surface detail
add_panel_lines(engine, object_id, *, spacing, depth, axis="z") -> DetailResult
add_greebles(engine, object_id, *, density, rest_fraction=0.4, seed=0) -> DetailResult

# material realism
vary_roughness(engine, material_id, *, base, spread, seed=0) -> DetailResult
clamp_albedo(rgb: tuple[float, float, float], *, metallic: bool = False) -> tuple[float, float, float]

# reporting
realism_report(engine, object_id) -> tuple[Measurement, ...]
```

## Layout

One file per responsibility, mirroring `src/measure/`'s split:

| File | Owns |
|---|---|
| `results.py` | `DetailResult` — the one result shape shared by every mutating pass |
| `edges.py` | `EdgeSelection`, `select_bevel_edges`, `bevel_width_for` — pure, no engine mutation |
| `apply.py` | `apply_edge_treatment` — the one function in the edge-treatment pairing that mutates the engine |
| `surface.py` | `add_panel_lines`, `add_greebles` |
| `materials.py` | `vary_roughness`, `clamp_albedo` |
| `report.py` | `realism_report` |

## Invariants

- **Edge selection is a proper subset, never everything.** `select_bevel_edges` on a plain box
  must select fewer than all twelve of its edges (`edges_test.py::test_a_plain_cube_selects_a_proper_subset`).
  An implementation that returns every edge has silently reintroduced the blanket bevel Gate A
  8.3 rejected.
- **Three independent filters, each provably wired up.** Dihedral angle
  (`acos(dot(n1, n2))` in degrees), convexity (sign test against the neighbouring face's
  plane — see `edges.py`'s docstring for the exact construction and its calibration against a
  known-convex box edge), and exposure (average of the two adjacent face normals' Z component;
  negative means facing away from world up and is treated as hidden). Each filter has a test
  that shows toggling it changes the outcome — a filter that never changes anything is not
  actually implemented, whatever the code looks like.
- **Bevel width scales with object size, never fixed.** `bevel_width_for` is `fraction` of a
  characteristic size of `snapshot.world_bounds()`, clamped into `[minimum, maximum]`, always
  strictly positive. This contract deliberately does not mandate which characteristic size
  (longest axis, diagonal, cube root of volume, ...) — `edges_test.py`'s example objects are
  sized so every reasonable choice lands on the same side of both clamps.
- **The engine's unapplied-scale refusal must reach the caller.** `apply_edge_treatment` never
  catches the `EngineError` `ModifierOps.bevel_edges` raises for an object with unapplied
  non-uniform scale — bevel width is computed in object space, so an unapplied scale would
  silently produce an uneven bevel, and the engine's own refusal is the only thing standing
  between that and a shipped defect.
- **A no-op is reported as a no-op.** `apply_edge_treatment` on an object with nothing
  qualifying, and `add_greebles` with `rest_fraction=1.0`, must both report `changed=False` and
  equal before/after triangle counts — never `changed=True` about geometry that did not move.
- **Detail passes are reproducible by seed.** `add_greebles` and `vary_roughness` must produce
  identical output for the same seed and, in practice, different output for different seeds. A
  pass that cannot be reproduced cannot be reviewed or undone meaningfully.
- **Albedo is clamped, not judged.** `clamp_albedo` moves pure black and pure white inside the
  physically plausible band (non-metal ~sRGB 60-240, metal ~sRGB 180-250 per
  `contracts.MaterialOps.set_pbr`'s docstring) and leaves anything already inside it — a
  mid-grey, say — untouched. Metal and non-metal have different floors.
- **`realism_report` never claims an overall score.** It returns only the four named,
  individually computable proxies (sharp-edge ratio, triangle aspect ratio, edge-length
  uniformity, triangle count); no published metric for "looks realistic" exists
  (`docs/research/domain.md`), and nothing in this report may be named or described as one.
  It is also read-only — it never calls a mutating `EngineProtocol` method.

## Contract gap

`contracts.MetricKind` has seven members; only `TRIANGLE_COUNT` names one of `realism_report`'s
four documented proxies directly. The other three have no dedicated member yet. See
`report.py`'s module docstring and this task's `contractRequests` output for the recommendation
to add them — until then, an implementation must reuse an existing `MetricKind` and carry the
proxy's real name in `Measurement.subject`/`Measurement.detail`.

## Dependencies

`contracts` only, at import time. `.pipeline/modules.json` lists `measure` as a design-time
dependency, but nothing in this module imports it — `realism_report`'s triangle count is
computed fresh from `engine.snapshot(object_id)`, not borrowed from `measure.triangle_count`,
because `measure` is itself still a throwing stub (do not depend on it).

## Testing

`pytest src/detail` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact commands
and current status.
