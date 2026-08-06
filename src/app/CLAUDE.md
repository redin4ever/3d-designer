# app — local conventions

See `README.md` for what this module is. This file is implementation-facing.

## Ownership

**Main-agent only** (Rule 5), like `contracts/` and `testing/`. This is the one place in
the repository allowed to import every module at once. That privilege is exactly why no
module agent may edit it — the moment a module owner adds its own wiring here, the
composition root stops being a single reconciliation point and becomes sixteen of them.

## Commands

```bash
python -m pytest src/app -q          # the end-to-end suite
python src/forge3d_cli.py doctor     # is it actually wired and startable?
```

`python` means `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`.

## Rules specific to this module

- **Never let a guarded import hide a real breakage silently.** Every `except` here logs
  and records into `MISSING_MODULES`, which `App.describe()` prints first. The failure mode
  this prevents: an agent discovering a capability is absent by trying to use it halfway
  through a build.
- **Coercion is schema-driven, never structural.** If you add a parameter type that needs
  converting, teach `_coercion_map` to recognise it from the JSON Schema. Do not add a rule
  that inspects the runtime value — `ratios=[0.5, 0.25, 0.1]` and a point are the same shape
  and only the schema distinguishes them.
- **`build_app` is the only function that knows the whole graph.** Keep it flat and
  readable; if a step grows logic, it belongs in its own file under `app/`, not in a longer
  `build_app`.
- **The fake-engine fallback must stay loud.** It is legitimate for a smoke test and useless
  for an asset. Anything that makes it quieter is a regression, however tidy.

## When you add a module

1. Add its handlers to `build_handlers` — with a guarded import, like the others.
2. If it publishes `*_SPECS`, add it to the coercion-source loop so its point parameters
   convert.
3. Add a line to `test_every_operation_module_reaches_the_registry` naming one of its
   operations. That test exists so a module can never be silently unreachable.
4. Update `docs/ARCHITECTURE.md`'s directory map.

## Why `app_test.py` matters more than its size suggests

Sixteen modules can each be green while none of them talk to each other. That is not a
hypothetical: this suite found `ScenePort.document` declared as a method against a property,
`ops` expecting `Vec3` where an agent sends JSON, and the MCP SDK shadowed by our own
package name. Two of those three could only ever have been found by putting the real objects
side by side.

When adding a test here, prefer one that drives a real journey over one that asserts a
wiring detail. The wiring assertions catch a missing import; the journeys catch a
misunderstanding.
