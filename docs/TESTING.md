# Testing

Two suites, both runnable on this machine today.

```bash
# backend — 609 test functions, plus 54 conformance checks run twice (fake + real Blender)
python -m pytest src -q

# frontend — 28 tests, pure logic, no browser and no WebGL
node --test frontend/tests/

# is the product actually wired and startable?
python src/forge3d_cli.py doctor
```

`python` here means `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`. The `python` on
PATH is the Windows Store alias stub and will not run anything.

## The one idea that makes this suite fast

`src/engine/` is the only module in the repository permitted to `import bpy`. Every other
module is written against `contracts.EngineProtocol` and receives an implementation at the
composition root. In tests that implementation is `testing.FakeEngine` — a real in-memory
mesh engine, not a mock that records calls.

The consequence: the entire decision layer runs in about a tenth of a second with no
Blender involved, and only `src/engine/`'s own tests need a real one.

The reason the fake is a real engine rather than a mock: a mock lets a wrong implementation
pass, because the test then asserts on the *conversation* rather than the outcome. With a
real fake you can assert that a railing post ended up plumb, instead of asserting that
`set_transform` was called.

## The `needs_blender` marker

```python
@pytest.mark.needs_blender
def test_something_that_needs_real_geometry(): ...
```

Skipped automatically when `bpy` is not importable. The root `conftest.py` prints whether
Blender was available in the test header, so a green run can never be mistaken for one that
silently skipped the engine.

**Blender is currently installed here, so these tests run.** They are not theoretical
coverage.

## The conformance suite — the reason the fake can be trusted

`src/engine/conformance*.py` holds check functions that take an engine. They are run twice:

- `conformance_test.py` runs them against `FakeEngine` — always.
- `blender_test.py` runs the same functions against real `bpy` — marked `needs_blender`.

If the two ever disagree, the fake has drifted from the thing it stands in for, and every
module tested against it is testing a lie. Three registries exist because a few checks
genuinely can only run one side: `UNIVERSAL_CHECKS`, `BLENDER_ONLY_CHECKS` (the fake's
boolean does not actually cut geometry, so bounds assertions on `difference` are
meaningless there) and `FAKE_ONLY_CHECKS` (asserting a solver argument was threaded through
needs the fake's call log; real bpy exposes no equivalent introspection).

## The end-to-end suite

`src/app/app_test.py` is the only place that drives the whole stack the way an agent
would — registry, write lock, scene log, real handlers, real measurement, real export.

It exists because sixteen modules can each be green while none of them talk to each other.
It has already earned its place three times: it caught `ScenePort.document` being declared
as a method while `Scene` exposed a property (both consumers and both their doubles agreed
with the declaration, so three suites passed and the real trio could never have worked),
`ops` expecting `Vec3` where an agent sends JSON lists, and the MCP SDK being shadowed by
our own package name.

Run it first when something feels wrong. A module suite tells you a module is consistent
with itself; this one tells you the product runs.

## Determinism

- Seed every source of randomness explicitly. `detail.add_greebles` takes a `seed` and the
  same seed must reproduce the same output — a detail pass that cannot be reproduced cannot
  be reviewed or meaningfully undone.
- No sleeps. Nothing here waits on wall-clock time; lease expiry is measured in operation
  count, not seconds, which is why the lock tests advance the clock by applying operations.
- Engine state is per-test. `FakeEngine` is constructed fresh by the `engine` fixture;
  real-Blender tests `reset()` in a fixture, because a shared `bpy` session is global
  mutable state and that is unavoidable in exactly one module.

## Where the stub boundary is

| Layer | Doubled by | Real thing exercised where |
|---|---|---|
| Blender | `testing.FakeEngine` | `src/engine/blender_test.py`, `src/app/app_test.py` |
| `scene` | `orchestration/conftest.py`'s `FakeScene` | `src/app/app_test.py` |
| MCP SDK | absence simulated via `sys.modules` | not exercised end to end — see below |
| WebSocket transport | lazy import, wiring tested | `serve()`'s live loop is not exercised |

Two honest gaps, stated rather than papered over: the MCP server's SDK-present code path
and the viewer's live socket loop are both reviewed but not driven by a test. Both need a
running client on the other end, which no unit test provides.

## Adding a test

Tests come first — no implementation exists before a test that fails for the right reason
(`.claude/rules/testing.md`). A test that fails with `ImportError` has not been verified;
stub the module until it fails on the assertion or a `NotImplementedError`.

Give every test a docstring saying what breaks *in the product* if it fails, not what the
test checks. `src/contracts/contracts_test.py` is the house style — every test there is
named after the failure it prevents.
