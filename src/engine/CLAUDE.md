# CLAUDE.md — `src/engine/`

Local conventions for whoever implements this module next. Read `README.md` first for what
the module is; this file is how to work in it without breaking the two-suite design.

## Boundary

- This is the only directory allowed to `import bpy`. Nothing outside it may, ever.
- Do not edit `src/testing/**`. `FakeEngine` is main-agent-owned, frozen infrastructure and
  the specification this module is tested against (Rule 5). If a conformance check's
  expectation genuinely cannot be met by any real bpy implementation, that is a contract
  request, not a license to change the fake or loosen the check.
- Do not edit `src/contracts/engine.py`. The Protocol is frozen; a needed change there is
  also a contract request.
- Only write inside `src/engine/`.

## TDD state

Every method currently raises `NotImplementedError("engine.<name>: not implemented")`. That
is RED (Rule 4): the conformance suite is real and already fails for the right reason. Your
job is GREEN — replace each raise with real bpy code until `pytest src/engine -q` (with a
real Blender available) is fully green. Do not change `conformance*.py` or the two `*_test.py`
files to make a failure go away; if a check seems wrong, it is a contract request to the main
agent, argued from the Protocol docstring in `src/contracts/engine.py`, not a local edit.

## Test / lint commands

```
pytest src/engine -q                     # both suites; blender_test.py auto-skips without bpy
pytest src/engine -q -m needs_blender    # real-bpy suite only — requires bpy importable
pytest src/engine -q -m "not needs_blender"  # fake-only, fast, no Blender needed
```

## File split

Follow the existing seams when a file grows — don't pile more onto `mesh.py` because it's
convenient; a new bpy concern gets a new file, mixed into `BlenderEngine` in `session.py`
the same way the existing five are. Same for `conformance_*.py`: a new check goes in the file
matching the `Ops` group it tests (or a new `conformance_*.py` for a concern with no actor
file of its own, e.g. `conformance_validation.py` for error-rule checks), and gets added to
`conformance.py`'s `UNIVERSAL_CHECKS`, `BLENDER_ONLY_CHECKS` or `FAKE_ONLY_CHECKS` tuple.

**Three registries, not two.** `FAKE_ONLY_CHECKS` exists for checks that can only run
against `FakeEngine` — e.g. because the only observable signal is `engine.calls` or another
non-`Protocol` `FakeEngine` accessor with no real-engine equivalent, or because the check
needs the root conftest's `engine_without_bake` fixture, which has no real-engine
counterpart. A check goes here only when it *cannot* be made to hold against `BlenderEngine`
even in principle — not as a shortcut. Register a new check in exactly one of the three
tuples and add exactly one wrapper test, in the one `*_test.py` file that tuple belongs to:
`UNIVERSAL_CHECKS` → both `conformance_test.py` and `blender_test.py`; `BLENDER_ONLY_CHECKS`
→ `blender_test.py` only; `FAKE_ONLY_CHECKS` → `conformance_test.py` only. Before writing a
new check as universal, actually run it against `FakeEngine` — `FakeEngine`'s crude
approximations (e.g. `bevel_edges` never moves a vertex; `boolean`'s `difference`/
`intersect` modes don't touch target geometry at all) have caught more than one
plausible-looking universal check that turned out to only hold for a real CSG/mesh engine.

## Conventions specific to this module

- Validate cheap, local preconditions (object exists, mesh is unwrapped, scale is applied)
  *before* touching anything that needs a live bpy context or windowed capability. See
  `conformance_surfacing.check_bake_requires_unwrap_first`'s docstring for why the ordering
  itself is a tested contract, not an implementation detail.
- Every `EngineError` needs a `suggestion` — a bare rule name with no next step makes an
  agent loop on the same failing call (Gate A 4.2).
- `RawOps.execute` must let a raising `source` propagate unwrapped. Wrapping it here (instead
  of leaving that to the caller, per the docstring on `RawOps.execute` in
  `src/contracts/engine.py`) breaks every call site's own `except Exception as exc: raise
  EngineError(...) from exc`.
- Keep `bpy` imports inside `src/engine/*.py` only — not, e.g., lazily imported from a
  neighbouring package "just this once". That is the whole point of this directory.
