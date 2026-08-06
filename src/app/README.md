# app — the composition root

Where sixteen modules become one product.

Every other module constructs only its own dependencies. Rule 5 keeps each one out of its
siblings, which is what made parallel construction safe — the cost is that somebody has to
do the wiring, once, in a place allowed to know about all of them.

```
engine  ──> Scene(engine, handlers)  ──> Orchestrator(scene)  ──> MCP registry
                  │                            │
                  └──> ViewerBridge ───────────┘
```

## Public interface

```python
from app import build_app, build_handlers, coerce_params

app = build_app(prefer_blender=True, include_raw=True, attach_viewer=True)
print(app.describe())
app.scene, app.orchestrator, app.engine, app.registry, app.viewer
```

`App.describe()` reports what is unavailable *first*. A tool that quietly starts with half
its capabilities missing is worse than one that refuses to start, because the agent finds
the gap by failing halfway through a build.

## Two things this module owns that nothing else could

**The handler registry.** `scene` replays a log by looking each `Operation.kind` up in a
`HandlerRegistry` and calling `handler(engine, op)`. Only `ops` was written to that shape;
`gaps`, `align`, `detail` and `uv` expose ordinary `fn(engine, object_id, **kwargs)`
functions, which is the right shape for a person and the wrong shape for replay.
`handlers.py` adapts them. Without it the registry is empty, every agent tool call resolves
to nothing, and sixteen green modules do nothing at all.

**JSON→domain coercion.** Everything an agent sends arrives as JSON: a point is
`[x, y, z]`, never a `Vec3`. `ops` documented — correctly — that params carry `Vec3`
internally and that converting from the wire shape belongs to whoever owns the boundary.
Every module honoured that and nobody built the boundary, so every point-taking operation
raised `AttributeError: 'list' object has no attribute 'x'` the first time a real agent
called it, while every module suite stayed green.

The coercion is driven by each tool's **own declared schema**, not by the shape of the
value. A structural guess — "a list of three numbers is a point" — would silently turn
`add_lod_chain`'s `ratios=[0.5, 0.25, 0.1]` into a coordinate. The schema pins a vec3 at
exactly three items while `ratios` is unbounded, so it can tell them apart and a guess
cannot.

## Invariants

- Guarded imports throughout: one broken module costs its own tools, never the whole
  registry. What was lost is recorded in `App.missing` and reported by `describe()`.
- The engine falls back to `testing.FakeEngine` when Blender is unavailable, **loudly**.
  The system genuinely runs either way, but the fake approximates non-planar primitives with
  bounding boxes and does not perform real boolean cuts — so anything it produces is a smoke
  test, never an asset. Saying so at startup is the difference between a limitation and a
  lie.
- A broken viewer never takes the geometry core with it.

## Tests

`app_test.py` is the only suite that drives the whole stack the way an agent would. It has
already earned its place three times — see `docs/ARCHITECTURE.md`'s "Corrections made during
the build". Run it first when something feels wrong: a module suite tells you a module is
consistent with itself; this one tells you the product runs.

```bash
python -m pytest src/app -q
python src/forge3d_cli.py doctor
```
