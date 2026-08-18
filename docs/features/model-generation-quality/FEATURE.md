# Model-generation quality

`add_impact_head` gives agents and local scripts a semantic hard-surface operation for the
relationships that failed in the first hammer: fitted armor, mechanically supported striking
faces, and a real handle socket.

## What it builds

One explicit parameter set produces a corner-clipped body, one inset top cap, front and rear cheek
plates, mirrored shoulder/collar/face stacks, replaceable striker inserts, retaining rims, and an
underside handle socket/collar. No plate or striking part receives an independent guessed position.

Parts remain material-ready and predictably named. For the regression artifact, representative ids
are `hero_head_top_plate`, `hero_head_cheek_front`, `hero_head_face_right`,
`hero_head_striker_left`, and `hero_head_handle_socket`.

## How it is wired in

- `src/ops/impact_head.py` — backend-neutral 16-part assembly geometry.
- `src/ops/registry.py` — REFINE tool schema with every visible dimension required.
- `src/ops/validation.py` — atomic fit rejection before any geometry is made.
- `src/ops/_acceptance.py` — 14 zero-gap checks covering armor and structural joints.
- `src/ops/_joinery.py` — explicit shoulder, striker, rim, and handle insertion depths.
- `src/ops/__init__.py` — public Python import surface.
- `src/app/impact_head_wiring_test.py` — live handler and JSON-vector reachability.
- `tools/create_hammer_asset.py` — real-Blender regression generator.

The app and MCP dispatcher need no per-operation branch: both already consume `OPS`, acceptance,
and joinery generically. This was verified rather than duplicated.

## Generation workflow

1. Block out the handle or host assembly.
2. Call `add_impact_head` during REFINE with explicit body, armor, shoulder, face, striker, rim,
   socket, and bevel dimensions.
3. Assign materials by deterministic part family; geometry creation does not hide style choices.
4. Re-run the persisted fit checks before phase promotion.
5. Render from a useful three-quarter view; geometry checks prove fit, while the image proves the
   silhouette and material hierarchy remain readable.

The final proof is `artifacts/futuristic_hammer.png`, with matching
`futuristic_hammer.blend` and `futuristic_hammer.glb` outputs.

## Decisions

See [decisions.md](decisions.md). The visual-QA striker addition is Q-25.

## Assumptions still standing

A-036 through A-044 remain reversible. The important boundaries are: one dual-strike family,
separate material-ready parts, explicit dimensions, and replaceable socketed striker inserts.

## Trace correction

The initial trace missed `src/ops/_shapes.py`; implementation showed that agent JSON origins also
need registration in `POINT_PARAMS`. The seam was added and wired before the feature gate.

## Noticed but not done

Asymmetrical axe/pick heads and a general arbitrary-surface armor-plate operation are separate
semantic families. They were not hidden as untested style branches inside this operation.

## Known gaps

The operation currently builds on world X with a centered vertical handle socket. A caller can
rotate the completed assembly afterward; arbitrary orientation is not yet a construction input.
