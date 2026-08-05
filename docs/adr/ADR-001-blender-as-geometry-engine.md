# ADR-001 — Blender 5.2 is the geometry engine

**Status:** accepted · **Date:** 2026-08-05 · **Source:** Gate A 9.2, 11.1

## Decision

Blender 5.2.0 LTS is the geometry engine. It is installed on the machine and verified
(`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`, build 2026-07-14). Python
3.13.14 is installed alongside it because `bpy` is version-locked to exactly 3.13.

## Context

The alternative was a Blender-free core (three.js + manifold-3d + gltf-transform), which research
recommended because neither Blender nor Python existed on the machine. The user chose Blender
and approved installing the toolchain, which removes the constraint that motivated the
alternative.

Gate A 7.3 — the codebase stays private and is never distributed — removes the GPL problem
entirely. Distribution is what triggers copyleft; private use does not. This is what makes
`import bpy` viable at all.

## Consequences

- Full access to Blender's modifier stack, bevel, boolean solvers, geometry nodes, UV unwrap,
  bake, and glTF exporter. None of these have to be reimplemented.
- **Blender's Python API breaks between versions with no deprecation policy.** 4.0 renamed
  Principled BSDF sockets, 5.0 renamed Grease Pencil to Annotation, 3.2 replaced context-override
  dicts with `temp_override`. Every version bump costs real migration work. We pin to 5.2 LTS
  (supported to 2028-07) and treat upgrades as scheduled work, not incidental.
- **Prefer the data API (`bpy.data`, `bmesh`) over `bpy.ops`.** Many operators `poll()`-gate on a
  window/screen/area that does not exist headless and throw `RuntimeError: context is incorrect`.
  Where an operator is unavoidable, wrap it in `bpy.context.temp_override()`.
- `bpy` as a module has no `bpy.context.window` at all — a stricter subset than `--background`.
  Any code path needing a window must go through a real Blender subprocess instead.

## Superseded by

Nothing.
