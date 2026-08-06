# uv

Full UV unwrap and baked texture maps, with the agent able to override seams by name.
Research flagged this as **the highest-risk area in v1** — seams and stretching are where
every existing AI-3D tool fails most visibly.

## Public interface

Everything importable from `uv` is declared in `uv/__init__.py`. Nothing else is public; do
not import `uv.seams`, `uv.bake`, `uv.quality`, etc. directly from outside this package.

```python
@dataclass(frozen=True)
class UVResult:
    object_id: str
    ok: bool
    seam_count: int
    coverage: float        # [0, 1], fraction of the UV tile occupied
    max_stretch: float      # worst measurable (world triangle area / uv triangle area)
    overlaps: int           # count of UV-space triangle pairs that genuinely intersect
    detail: str = ""

@dataclass(frozen=True)
class BakeResult:
    object_id: str
    ok: bool
    maps: dict[str, str]              # {channel: filepath}
    unavailable_reason: str = ""      # populated iff EngineUnavailable was reported
    uv: UVResult | None = None        # see "bake policy" below for exactly when this is set

suggest_seams(snapshot, *, min_dihedral_deg=60.0) -> tuple[int, ...]
unwrap(engine, object_id, *, seams=None, method="angle_based", margin=0.001) -> UVResult
bake(engine, object_id, *, channels=("albedo","normal","roughness"),
     resolution=1024, output_dir=".") -> BakeResult
uv_quality(engine, object_id) -> tuple[Measurement, ...]
unwrap_and_bake(engine, object_id, **kw) -> BakeResult

UV_SPECS: tuple[ToolSpec, ...]   # roles=(ToolRole.POLISH,), mutating=True
```

## Layout

One file per responsibility:

| File | Owns |
|---|---|
| `results.py` | `UVResult`, `BakeResult` — the two outcome shapes |
| `seams.py` | `suggest_seams` — pure, no engine mutation |
| `quality.py` | `uv_quality`, and `compute_uv_proxies` (the shared pure computation `unwrap` also reuses) |
| `_uv_geom.py` | Private: 2D triangle area and triangle-triangle overlap (Separating Axis Theorem) |
| `unwrap.py` | `unwrap` — the one function that calls `mark_seams` + `unwrap` on the engine |
| `bake.py` | `bake`, `unwrap_and_bake` |
| `specs.py` | `UV_SPECS` |

## Invariants

- **`suggest_seams` returns a proper subset, never every edge.** A triangulated cube has 18
  edges (12 real + 6 fan-triangulation diagonals, each perfectly flat at 0 degrees); at the
  default 60-degree threshold only the 12 real edges qualify. Raising the threshold returns
  strictly fewer — proven against a hand-built folded strip in `seams_test.py`, since a plain
  cube's uniform 90-degree edges cannot show a *graded* threshold response on their own.
- **An agent-supplied `seams=` argument always overrides the suggestion outright**, never
  merged or filtered against it — including an empty tuple, which means "no seams", not "use
  the default". `unwrap_test.py` proves the override reaches `EngineProtocol.mark_seams`
  unchanged via the recorded call, since `FakeEngine.unwrap`'s planar-projection UV layout
  does not itself react to which edges are marked (see that file's own docstring).
- **An out-of-range seam index is rejected with `ValueError` before it reaches the engine**,
  whether it came from `suggest_seams` (impossible by construction — it only emits positions
  inside `range(len(snapshot.edges()))`) or from an agent-supplied `seams=` argument (checked
  explicitly in `unwrap()`). An out-of-range index would otherwise silently seam whichever
  edge happens to sit at that position at the engine end, with no error at all.
- **`EngineUnavailable` is reported by name, never swallowed into a generic failure.**
  `bake()` and `unwrap_and_bake()` catch only `contracts.EngineUnavailable` and turn it into
  `BakeResult(ok=False, unavailable_reason=...)` — every other exception (an unknown object,
  a bad resolution, …) propagates unchanged. Confusing the two would make it impossible for a
  caller to tell "install Blender's dependencies" apart from "your mesh or arguments are
  broken" (see `bake_test.py::test_bake_propagates_a_non_unavailable_engine_error_rather_than_swallowing_it`).
- **Bake policy — "bake before any unwrap" resolves to "unwraps first, lazily":** `bake()`
  calls `unwrap()` automatically only when the object has no UVs yet
  (`snapshot.uvs is None`), using `suggest_seams`'s automatic result, and its `BakeResult.uv`
  is populated exactly in that case — an object that already has UVs (including from an
  explicit, seam-overridden `unwrap()` call) is left alone and `BakeResult.uv` stays `None`.
  This was chosen over "fail cleanly and demand a prior `unwrap()` call" because every caller
  reachable from `bake()` already knows how to produce a usable UV layout on its own, and a
  second required call buys no benefit. `unwrap_and_bake()` is different on purpose: calling
  it *is* the request to (re)unwrap, so it always unwraps and its `BakeResult.uv` is always
  populated — this is what lets a fresh `seams=` override reach the engine even for an object
  baked once already.
- **Baking an unknown channel name does not crash.** Channel names are not validated against
  an allowlist in this module or in `EngineProtocol.bake` — an unrecognised name simply comes
  back as its own key in `BakeResult.maps`, exactly like a recognised one.
- **`uv_quality` never mutates the engine**, and reads as the identity value (0.0 coverage,
  0.0 stretch, 0 overlaps) rather than raising when the object has no UVs yet.
- **`UV_SPECS` are fully constructed `ToolSpec` data, not stubs** — both entries mutate
  (`unwrap_uvs`, `bake_textures`) and neither is visible to `ToolRole.INSPECT`; the read-only
  `uv_quality` query has no entry here on purpose (see `specs.py`'s module docstring).

## Known simplification: per-vertex UVs

`contracts.MeshSnapshot.uvs` is one coordinate per **vertex**, not per triangle corner. A
real cut-and-unfold unwrap needs per-corner UVs, since the same vertex can carry different
coordinates on either side of a seam — this is a limitation of the frozen contract this
module is built against, not something invented here (see `.pipeline/contract-requests.json`
candidate: `MeshSnapshot` growing an optional per-corner UV representation).

One consequence worth knowing: `FakeEngine.unwrap` (`src/testing/fake_surfacing.py`) projects
straight onto world X/Y, ignoring Z. On a cube this means the top and bottom faces — which
share the same X/Y footprint — land on exactly the same UV triangles. This is a **genuine,
engine-produced overlap**, not a contrived test fixture, and `quality_test.py`'s overlap tests
rely on it directly (contrasted with a single flat plane, which the same projection maps onto
the unit square with zero overlap). A real Blender unwrap would not have this problem; the
fake's simplicity is what makes it useful for exercising the overlap detector without hand
authoring degenerate UVs.

## Dependencies

`contracts` only at runtime (`.pipeline/modules.json` lists `measure` as a design-time
dependency for integration ordering; nothing in this module currently imports it — every
computation here is `MeshSnapshot`/`EngineProtocol` primitives directly, the same boundary
`measure` itself is built against).

## Testing

`pytest src/uv -q` from the repo root. Every test takes the shared `engine` and
`engine_without_bake` fixtures (`conftest.py`) — both `FakeEngine`, no Blender required. See
`CLAUDE.md` for the exact commands and file layout.
