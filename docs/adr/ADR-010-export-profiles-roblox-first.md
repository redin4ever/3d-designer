# ADR-010 — Per-engine export profiles, Roblox first

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 12.1, 12.2, 12.3, 6.2, 6.3

## Decision

Export runs through **named engine profiles**, each owning its own axis, handedness, unit and
budget rules. Four ship in v1, **Roblox as the primary** (Gate A 12.1, verbatim: *"it should
manage for all as i might use roblox's engine usually"*).

| Profile | Up | Handedness | Unit | Notes |
|---|---|---|---|---|
| **Roblox** | Y | right | stud (1 stud = 0.28 m) | Per-MeshPart triangle ceiling; needs the tightest budget checks |
| Unity | Y | **left** | metre | Requires an X-axis flip **and** a rotation-sign correction — a positive rotation is CW in Unity, CCW in glTF |
| Unreal | Z | **left** | centimetre | Scale ×100 from the internal metre convention |
| Godot | Y | right | metre | Closest to glTF's own convention; least conversion risk |

## Context

The Blender Z-up-right-handed → glTF Y-up-right-handed → Unity Y-up-**left**-handed chain is a
documented, repeatedly-reported bug source. Its signature is mirrored geometry or inverted
rotations that appear only after a full export→import round trip — discovered in a different tool
than the one that caused it, which is what makes it expensive.

Gate A 6.2 locks the internal convention at 1 unit = 1 metre (changeable per scene). Profiles
convert *at the boundary*; nothing upstream of export knows about engine conventions.

## Consequences

- **One audited conversion function per profile**, tested with a round-trip fixture that would
  catch a mirror or a rotation-sign inversion. This is the single place handedness is allowed to
  be reasoned about.
- Polygon budgets are **per-profile and per-asset-class**, tracked and warned against, never
  enforced (Gate A 12.2). Detail passes are what run the count up, so the warning fires where it
  is useful.
- **LODs and modular snapping pieces** ship in v1 (Gate A 12.3). Collision meshes and texture
  atlasing were offered and not selected — they go to the backlog at low priority.
- Roblox's stud unit means its profile is the one most likely to surface scale bugs, which is an
  argument for it being the primary rather than against it.

## Superseded by

Nothing.
