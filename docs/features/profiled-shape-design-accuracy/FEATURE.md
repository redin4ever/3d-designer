# Profiled-shape design accuracy

`add_profiled_solid` gives connected agents and local generators a middle-grain shape
operation between six basic primitives and a narrowly semantic whole assembly. It builds one
closed solid from corresponding two-dimensional sections along a selected world axis.

Two identical sections produce an exact extrusion. Changing section size, centre or outline
produces a continuous loft. This covers an anvil body and horn, a tapered extraction hood,
architecture details such as brackets and columns, and furniture legs without pretending those forms are stacks
of cubes, cones and cylinders.

## Calling contract

Every call supplies:

- `object_id`: deterministic id of the resulting mesh;
- `origin`: world `[x, y, z]` in metres;
- `axis`: `x`, `y` or `z`;
- `sections`: at least two `{offset, profile}` records;
- `bevel_width`: explicit metres, including `0` for modeled sharp edges.

Offsets are strictly increasing along the selected axis. Each profile is a closed convex polygon
listed counter-clockwise in its local `[u, v]` plane. Every section uses the same vertex count and
point correspondence. For a horizontal X or Y run, local V remains world-up; for Z, local U/V map
to world X/Y.

```python
perform(
    "add_profiled_solid",
    object_id="hood",
    origin=[0.0, 0.0, 2.8],
    axis="z",
    sections=[
        {"offset": 0.0, "profile": [[-1.5, -0.8], [1.5, -0.8], [1.5, 0.8], [-1.5, 0.8]]},
        {"offset": 1.5, "profile": [[-0.4, -0.3], [0.4, -0.3], [0.4, 0.3], [-0.4, 0.3]]},
    ],
    bevel_width=0.015,
)
```

## Failure and verification

The operation rejects atomically before creating geometry when sections are missing, unordered,
clockwise, non-convex, duplicated, malformed, or inconsistent in vertex count. It never silently
sorts, reverses or rescales caller geometry. A bevel that consumes the smallest station gap or
profile edge is rejected with the measured limit.

Runtime acceptance requires positive volume and forbids boundary holes, non-manifold edges or
vertices, loose/duplicate geometry, flipped normals and self-intersection. Exact world bounds are
pinned for all three axes in both the in-memory engine and real Blender. Appearance remains a
render-review decision; topology checks do not claim a shape is aesthetically convincing.

## Forge regression

The blacksmith generator now uses profiled solids for its continuous anvil body, hardened face,
tapered extraction hood and leather bellows. Those meshes remain separate for material assignment
and later editing. The saved BLEND, GLB and PNG are regenerated, then the five profiled hero meshes
are inspected from the saved Blender file so modifier or export-side topology damage cannot hide
behind clean source parameters.

## How it is wired in

- `src/ops/profiled_solid.py` owns validation, mesh construction and structural acceptance.
- `src/ops/registry.py` exposes the operation to REFINE agents and replay dispatch.
- `src/app/` and `src/mcp_server/` pin composition-root reachability and the visible tool count.
- `tools/create_blacksmith_forge_asset.py` is the concrete visual and export regression.

## Decisions

The full decision record is in [decisions.md](decisions.md).

## Assumptions still standing

A-045 through A-052 remain standing: one explicit convex-profile tool, atomic rejection,
structural acceptance, separate editable parts, game-ready density, and anvil/hood-first forge
coverage. Reversal costs are recorded in `docs/ASSUMPTIONS.md`; none require changing existing
primitive behavior.

## Noticed but not done

Concave and mixed-vertex-count lofts remain outside this feature because their correspondence and
triangulation policies need a separate tested design. Cinematic subdivision and displacement are
also separate from the requested accurate, editable construction workflow.

## Known gaps

The repository instructions name `.pipeline/check.mjs`, but that script is absent in this checkout.
The mandatory feature gate, complete backend/frontend suites, product doctor, saved-file topology
audit, and render inspection were run instead. Nothing is quarantined or unfinished within the
declared convex profiled-solid scope.
