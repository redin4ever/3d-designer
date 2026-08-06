# mcp — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing: conventions, status, and the reasoning behind the non-obvious
choices, for whoever picks this up next.

## Status

**GREEN.** Written test-first against the module brief, `src/contracts/operations.py`,
`docs/adr/ADR-003-mcp-server-dual-transport.md` and `docs/adr/ADR-009-unrestricted-execution-local-trust.md`
(Rule 4): every function started as a throwing `NotImplementedError("mcp.<name>: not
implemented")` stub (`SERVER_INFO` excepted — real, constructed data from the start, same
reasoning as `raw.RAW_TOOL_SPEC`), `pytest src/mcp -q` was run and confirmed 28 of 29 tests
failing on that error specifically before any real implementation existed, and only then
was each function implemented. `pytest src/mcp -q` now passes 29/29; `pytest src -q` passes
579/579 with this module included.

Two of the SDK-absence tests in `transports_test.py` explicitly reject
`NotImplementedError` rather than trusting a bare `pytest.raises(RuntimeError)` —
`NotImplementedError` is itself a `RuntimeError` subclass, so a naive version of that test
would have spuriously passed against the throwing stub and never actually verified
anything. Caught by inspecting the RED-phase failure list line by line rather than trusting
the pass/fail count alone; see `transports_test.py`'s module docstring.

## Commands

```bash
# this module only
python -m pytest src/mcp_server -q

# one file
python -m pytest src/mcp_server/dispatch_test.py -q

# whole decision layer (sanity check you haven't broken a neighbour)
python -m pytest src -q
```

No `needs_blender` marker anywhere in this module — everything here runs against
`orchestration.Orchestrator` backed by this module's own `FakeScene` double
(`conftest.py`), with no Blender and no real `src/scene/` installed, and must stay that
way.

## Boundaries

- Write only inside `src/mcp_server/**`. Everything else — `src/contracts/`, `src/ops/`,
  `src/export/`, `src/raw/`, `src/gaps/`, `src/align/`, `src/uv/`, `src/measure/`,
  `src/detail/`, `src/orchestration/` — is a frozen or sibling-owned surface (Rule 5):
  read freely, never edit.
- `mcp_server/__init__.py` is a barrel: re-exports only. If it grows logic, that logic belongs in
  one of the responsibility files instead.
- Nothing outside `mcp/` may import `mcp.registry`, `mcp.dispatch`, etc. directly — only
  `from mcp_server import <name>`, per `mcp_server/__init__.py`'s `__all__`. `mcp._cap`, `mcp.validation`
  and `mcp.serialize` are module-private (leading underscore or simply not re-exported) —
  exercised transitively through `build_registry`/`dispatch`, the same pattern
  `orchestration/_tool_registry.py` uses.
- Do not import `bpy`. Nothing in this module needs it, and importing it would make the
  whole registry/dispatch surface depend on a real Blender install for no reason.
- Sibling registry modules (`measure`, `gaps`, `align`, `uv`, `detail`) may not all exist,
  or may not all publish a `*_SPECS` constant yet — `registry.py`'s `_load_optional`
  guards every one of those five imports individually (`ImportError` *or*
  `AttributeError`, both swallowed) rather than assuming any particular subset is ready.

## Implementation notes for whoever picks this up

- **`dispatch`'s check order is role visibility -> param validation -> write lock ->
  execution**, in that order, on purpose: a caller with no lease yet still deserves to
  learn its params are wrong before it bothers acquiring one
  (`dispatch_test.py::test_missing_parameter_check_runs_before_the_lock_check`).
- **Every current `ToolSpec` in this codebase has `handler=None`.** Registry *content*
  modules (`ops`, `export`, `raw`, `gaps`, `align`, `uv`) deliberately leave execution to
  the operation log rather than attaching a callable — see `export/registry.py`'s own
  docstring. `dispatch`'s live path for a mutating, handler-less tool therefore builds a
  `contracts.Operation` named after the tool and runs it through
  `orchestrator.perform(op, lease)`. The `spec.handler is not None` branches in
  `dispatch.py` are real, correct code with no current caller — they exist so a future
  module that *does* attach a handler does not need `dispatch.py` touched at all.
- **The REFINE-role cap (`_cap.py`) is the one genuinely surprising piece of this
  module.** `ops` (4) + `gaps` (8) + `align` (7) = 19 tools under `ToolRole.REFINE` as of
  this writing, entirely because three independently-built, independently-correct modules
  each landed on the same role with no shared count. See `README.md`'s "The REFINE-role
  cap" section before changing `_cap.py`'s round-robin — a naive "first N in source order"
  cap was tried first and rejected specifically because it zeroed `align` out completely
  (see the git history of this file if the reversion is still there). If a sibling module
  ships new `REFINE` (or any other role's) content later and a role's count changes,
  `_cap.py` requires no change — it reacts to whatever `_sources()` collects.
- **The `mcp_server` package name collision is real and already load-bearing**:
  `pyproject.toml` lists `mcp>=1.2.0` as a dependency — the same top-level import name as
  this package. `transports.py`'s `_load_sdk` cannot resolve this from inside
  `src/mcp_server/**` (Rule 5 — outside this module's write boundary is also outside its power to
  fix via import tricks alone, since the conflict is in `sys.path` ordering set by the
  root `conftest.py` / whatever process starts the real server). Flagged, not worked
  around; see `README.md`.
- **`serve_stdio`/`serve_http`'s SDK-present code paths are unverified.** The SDK is not
  installed in this environment (`pip list` has no `mcp_server` package despite
  `pyproject.toml` naming it — the environment has not run `pip install -e .[dev]`
  against the current `pyproject.toml`). Every test that can run without the SDK does;
  the two that would need it do not exist, rather than being written against a guess and
  silently passing for the wrong reason. Re-verify `_build_server`'s handler wiring
  (`list_tools`/`call_tool` decorator shape) against the SDK's actual API the first time
  it is genuinely installed and reachable.
- **`downscale_image` operates on binary PPM (`P6`) bytes, not PNG/JPEG.** This codebase
  has no Pillow dependency, and `numpy` (an actual `pyproject.toml` dependency, already
  installed in this environment) was deliberately not reached for either — no other
  module under `src/` uses it, and pure-Python nearest-neighbour resize over the small
  images this module's own tests construct is fast enough not to need it. Revisit if a
  real render pipeline needs a real codec — that is a dependency decision for a gate, not
  something to add quietly here.
- **`validate_params`/`to_jsonable` are private, not part of the public barrel.** Both are
  exercised only transitively through `dispatch_test.py`, per `.claude/rules/testing.md`'s
  "test the public interface" guidance — the same reasoning
  `orchestration/_tool_registry.py` follows for `tools_for`.

## Test layout

Mirrors the responsibility files, minus the two private ones (exercised transitively):

| Test file | Covers |
|---|---|
| `registry_test.py` | role tool-set bounds, the REFINE cap, the raw tool's on/off switch and role scoping, description/unit conventions |
| `dispatch_test.py` | role gating, param validation, the write lock, the happy path, `raw_execute`'s opaque flag |
| `images_test.py` | `downscale_image` — large shrinks, small/at-bound left alone, aspect ratio |
| `transports_test.py` | `SERVER_INFO`, SDK-absence errors, the ADR-009 loopback warning |

`conftest.py` holds `FakeScene` (mirrors, but does not import, `orchestration/conftest.py`'s
own private double — that module's boundary rules keep it test-suite-private) plus
`orchestrator`/`write_lease` fixtures every dispatch test needs.

## Style

Follows the repository-wide conventions in the root `CLAUDE.md` and the house style
visible in `src/contracts/contracts_test.py`, `src/raw/raw_test.py` and
`src/orchestration/`: dataclasses over dicts, `from __future__ import annotations`, and a
docstring on every test stating the product-level consequence of the test failing — not
just what it checks.

## Open items for the main agent

- **Cross-module coordination**: `ToolRole.REFINE` is over-subscribed once `ops` + `gaps`
  + `align` are all counted together (19 declared, 8 visible by default after this
  module's cap). See `README.md`'s "The REFINE-role cap" for the three candidate real
  fixes; none of them are this module's to make alone.
- **Package name collision**: `src/mcp_server/` and the `mcp>=1.2.0` PyPI dependency share a
  top-level import name, and `src/`-first `sys.path` ordering means this package always
  wins. Needs a decision at a gate (rename this package, or alias the SDK at process
  start) before `serve_stdio`/`serve_http` can be exercised against a real install.
