# Host-aware surface details

Roof windows, raised wall signs, and façade ribs now attach to measured host geometry
instead of guessed world coordinates and quaternions. The factory regression artifact has
been regenerated with these operations.

## What changed

- `add_roof_window` finds the dominant upward planar face of a named roof panel, derives
  its horizontal/up-slope frame, checks the requested footprint, then creates a joined
  frame and glass that contact and follow that plane.
- `add_wall_sign` selects the exterior vertical face aimed at `toward`, centers portable
  extruded mesh text horizontally at the requested world height, and removes it atomically
  if the actual glyph bounds do not fit inside the wall margin.
- `add_facade_ribs` projects the wall's current triangles after openings have been cut.
  Each rib is intersected with those remaining solid regions at its full width, shortened
  by `opening_clearance`, and segments below `min_segment` are omitted. The output remains
  one predictable joined object even when a rib is split above a garage or window.
- `measure_surface_angle` makes face-normal alignment directly inspectable. Roof windows
  and signs persist one-degree alignment and 1 mm contact acceptance queries.

## Failure prevention

The operations reject unknown or unsupported hosts, invalid dimensions and fractions,
oversize details, empty text, and details that do not fit before leaving partial geometry.
Placement is recalculated from the live host snapshot on replay, so moving or rebuilding a
roof/wall cannot preserve a stale hand-authored rotation.

The factory generator contains no raw font conversion, skylight quaternion helper, or
full-height front rib loop. An app-level regression pins those constraints, while
fake-engine and Blender conformance tests cover the centered exportable text boundary.

## Agent workflow

1. Build roof panels and walls, then cut all wall openings.
2. Add roof windows to a specific roof panel and provide normalized horizontal/up-slope
   fractions.
3. Add signs using an exterior `toward` point and an explicit center height.
4. Add façade ribs only after openings, with explicit spacing, width, depth, edge margin,
   opening clearance, and minimum retained segment.
5. Inspect surface angle/contact acceptance and visually review the finished render.

## Decisions and assumptions

See [decisions.md](decisions.md). A 50 mm opening clearance and 100 mm minimum retained rib
segment are supplied explicitly by the factory generator; they are not hidden library
defaults. Current surface selection supports planar upward roof faces and vertical wall
faces.

## Proof

- Unit and integration coverage: `surface_mounts_test.py`, `facade_ribs_test.py`,
  `surface_angle_test.py`, engine text conformance, registry/validation assumption sweeps,
  and `surface_mount_wiring_test.py`.
- Regenerated outputs: `artifacts/factory.blend`, `artifacts/factory.glb`, and
  `artifacts/factory.png`.

## Known limits

- Curved and multiply folded host faces are rejected rather than approximated.
- Roof windows are surface-mounted framed assemblies; this operation does not cut glazing
  holes through the roof slab.
