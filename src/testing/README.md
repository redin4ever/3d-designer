# testing — the shared test engine

`FakeEngine` is a pure-Python `EngineProtocol` implementation with no `bpy`. It is what
makes the whole decision layer testable in a tenth of a second on a machine with no Blender.

## It is a real engine, not a mock

This is the important design decision here. A mock that records calls lets a wrong
implementation pass, because the test then asserts on the *conversation* rather than the
outcome — you learn that `set_transform` was called, not that the post ended up plumb.

`FakeEngine` maintains actual vertices, faces and transforms, so a test can assert on
geometry:

```python
def test_posts_stay_plumb(engine):
    engine.create_primitive("post", "cube", Vec3(0.05, 0.05, 0.9))
    ids = engine.array_along_curve("post", rake, spacing=1.0, keep_upright=True)
    for oid in ids:
        up = engine.snapshot(oid).transform.rotation.rotate(WORLD_UP)
        assert up.z == pytest.approx(1.0)
```

`engine.calls` exists for the rare case where the geometric outcome genuinely cannot show a
difference — proving a boolean used the `exact` solver, for instance. Assert on geometry
first; reach for the call log only when it cannot.

## What it deliberately does not do

Honest limits, because a test that passes here and fails against Blender is worse than no
test:

- **Non-planar primitives are bounding-box approximations.** A "sphere" is a box. The fake
  exists to exercise placement, measurement and bookkeeping, not to reproduce Blender's
  tessellation — nothing should assert on a primitive's tessellated shape.
- **`boolean` does not actually cut.** `union` joins; `difference` and `intersect` adjust
  bookkeeping only. Any assertion about the *geometry* of a difference belongs in
  `BLENDER_ONLY_CHECKS`.
- **`bevel_edges` does not move vertices.** It models polygon growth so budget tests are
  meaningful, nothing more.
- **`unwrap` is a planar XY projection.** Enough to assert UVs exist and stay in range; not
  a real unwrap.

Construct it with `bake_supported=False` to exercise the `EngineUnavailable` path — in-process
Blender can genuinely lack a windowed context, and that must arrive as a named capability
failure rather than a crash.

## The conformance suite is what keeps it honest

`src/engine/conformance*.py` holds check functions run against **both** `FakeEngine` and
real `bpy`. If the two disagree, the fake has drifted from the thing it stands in for and
every module tested against it is testing a lie. See `docs/TESTING.md`.

## Files

| File | Holds |
|---|---|
| `fake_engine.py` | `FakeEngine`, `FakeObject` — mesh, modifier and lifecycle operations |
| `fake_surfacing.py` | materials, UV, bake, export, raw — split as a distinct actor |
| `mesh_helpers.py` | stateless geometry: `unit_cube`, `sample_polyline`, `boundary_loops`, … |
| `fake_engine_test.py` | tests for the fake itself |

The fake is depended on by every other module's suite, so a bug here produces false
confidence everywhere at once. It gets its own tests for the same reason a shared library
does.
