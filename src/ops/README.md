# ops

The construction library. Typed, parametric operations with named, validated parameters —
`add_railing(path, height, baluster_gap, post_spacing)` — not primitives (`add_cube`,
`move`, `rotate`: a railing takes ~140 of them and drift accumulates across every one) and
not whole-object composites (`build("a staircase")`: measured at -12.6% Exec@1 because the
model has to get a dozen parameters right at once with no intermediate check). ADR-004.

Every operation here is validated on entry and re-measurable on exit — that pairing is what
makes ADR-005's programmatic definition-of-done possible: the acceptance check re-runs the
same query the parameters defined, rather than trusting the agent's own report of success.

`add_railing` is the flagship. It is the user's own worked example of why this library
exists at all, and it is what most of this package's tests are about — see `railing.py` and
`railing_test.py`.

## Public interface

Everything importable from `ops` is declared in `ops/__init__.py`. Nothing else is public;
do not import `ops.railing`, `ops.stairs`, etc. directly from outside this package.

```python
OPS: HandlerRegistry            # {kind: OperationHandler} — what scene replays through
OP_SPECS: tuple[ToolSpec, ...]  # MCP declarations, roles=(BLOCKOUT,) or (REFINE,)

add_primitive(engine, op) -> OperationResult
add_wall(engine, op)      -> OperationResult   # start, end, height, thickness
add_floor(engine, op)     -> OperationResult   # width, depth, thickness
add_gable_roof(engine, op) -> OperationResult  # panels, ridge, rake/eave trim, corner caps
add_opening(engine, op)   -> OperationResult   # boolean a door/window out of a wall
add_staircase(engine, op) -> OperationResult   # treads, rise, run, width
add_staircase_to_landing(engine, op) -> OperationResult # derives direction/rise/run
add_railing(engine, op)   -> OperationResult   # THE flagship — see railing.py
array_along(engine, op)   -> OperationResult
add_lod_chain(engine, op) -> OperationResult   # ratios -> progressively simpler copies
add_modular_kit(engine, op) -> OperationResult # grid-aligned tiling pieces

validate_params(kind: str, params: dict) -> dict          # raises ToolError naming the bad param
acceptance_for(kind: str, params: dict) -> tuple[AcceptanceQuery, ...]
```

`OPS` and `OP_SPECS` are real, constructed values — never stubs. Every handler function is
a throwing stub (see `CLAUDE.md` for status).

## Layout

One file per responsibility, so two agents extending different operations never touch the
same file:

| File | Owns |
|---|---|
| `primitives.py` | `add_primitive` |
| `architecture.py` | `add_wall`, `add_floor`, `add_opening` |
| `stairs.py`, `landing_stairs.py` | legacy raw-run and landing-derived supported stairs |
| `roof.py` | detailed parametric gable roof assembly |
| `railing.py` | `add_railing` — the flagship |
| `arrays.py` | `array_along`, `add_lod_chain`, `add_modular_kit` |
| `validation.py` | `validate_params`, `acceptance_for` |
| `registry.py` | `OPS`, `OP_SPECS` |

Test files mirror this layout exactly, one `<file>_test.py` per `<file>.py`. `railing_test.py`
carries the most tests in the package on purpose — see its module docstring.

## Invariants

- **A railing's posts are plumb in world +Z, regardless of the path's slope.** A post
  normal to a stair rake — aligned to the path tangent instead of world up — is *the*
  single most common naive-generator error (`contracts.ConstraintKind.PLUMB`). This must
  hold on a level path and on a 31-degree rake alike.
- **Posts are forced at every direction change**, in addition to the regular pitch. A fixed
  spacing with no corner resampling leaves a corner either short a post or straddled by a
  doubled one.
- **A top rail terminates at post centrelines**, not at an arbitrary parametric interval.
- **A baluster's `baluster_gap` is the clear, surface-to-surface opening** — never the
  centre-to-centre pitch, which is always wider by the balusters' own width.
- **Spacing and count are always measured along the path's own arc length**, never along
  its horizontal or straight-line projection. This is what makes a rake come out right.
- **Every operation's parameters are validated on entry.** A negative dimension, a zero
  count, or a spacing that cannot fit the path is a named `ToolError` with a `suggestion`,
  never a bare `KeyError`/`ValueError`/traceback (Gate A 4.2).
- **Every operation kind returns at least one `AcceptanceQuery`.** An operation nobody can
  re-check is an operation nobody can trust the agent's own claim about (ADR-005).
- **`OPS` and `OP_SPECS` cover exactly the same 21 kinds, in both directions.** A handler
  with no tool is unreachable; a tool with no handler crashes at call time.
- **No operation tool is ever exposed to the `INSPECT` role.** Every one of them mutates
  the scene; `contracts.ToolSpec.__post_init__` enforces this at construction time
  (ADR-007), and `registry_test.py` guarantees the registry never tries to violate it.
- **Produced object ids are predictable from `op.op_id` and index** (posts, balusters,
  treads, kit pieces), so a later operation or constraint can reference one specific part
  without needing this module to tell it what the id was.
- **No dependency on `src/constraints/` or `src/measure/` behaviour.** Both are stubs
  themselves; whatever this module needs to know about geometry is computed directly from
  `engine.snapshot`/`engine.world_bounds`.

## Dependencies

`contracts` and `testing` (in tests only, via the root `engine` fixture). No `bpy`, ever. No
runtime dependency on `constraints` or `measure` — see `CLAUDE.md`.

## Testing

`pytest src/ops` from the repo root. Every test takes the shared `engine` fixture
(`conftest.py`) — a `FakeEngine`, no Blender required. See `CLAUDE.md` for the exact
commands and current red/green split.
