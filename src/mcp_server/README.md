# mcp_server

The MCP server: registry policy, dispatch, role-and-phase authorisation, the session tools,
both transports, image downscaling (ADR-003). This is the module through which everything
the rest of the product builds becomes reachable by a connected agent. Gate A 7.4, verbatim:
*"also make sure it supports my subscriptions eg: chatgpt subscription so that i can use it
with it."* MCP is the only path where a consumer subscription drives the tool with no
per-token billing layered on top, which is why both transports exist: **stdio** for Claude
Desktop / Claude Code / Cursor, **streamable HTTP** for ChatGPT developer-mode connectors.

Registry **content** — what a tool does — is declared beside each operation
(`ops.OP_SPECS`, `export.EXPORT_SPECS`, `raw.RAW_TOOL_SPEC`, and `measure`/`gaps`/`align`/
`uv`/`detail`'s `*_SPECS` constants). Registry **policy** — which of the nine
`contracts.ToolRole` values sees which tools, which execution route each takes, how a call
is validated, authorised and locked, how an oversized render gets downscaled before it costs
15-25k tokens instead of ~1,600 — lives here.

## Public interface

Everything importable from `mcp_server` is declared in `mcp_server/__init__.py`:

```python
def build_registry(*, include_raw: bool = True) -> dict[ToolRole, tuple[ToolSpec, ...]]
    # collects OP_SPECS, the export specs with handlers attached, SESSION_SPECS,
    # RAW_TOOL_SPEC and measure/gaps/align/uv/detail's *_SPECS where they exist,
    # and partitions by role. Nothing is capped, trimmed or hidden.

def tools_for(role: ToolRole) -> tuple[ToolSpec, ...]
    # role's slice of the default registry (include_raw=True)

def dispatch(name: str, params: dict, *, role=None, orchestrator, lease=None) -> dict
    # find tool -> validate params -> lease required? -> authorise (phase + lease) ->
    # execute -> JSON-serialisable result.  `role` is accepted and IGNORED (ADR-013).

def serve_stdio(orchestrator) -> None       # blocking; Claude Desktop/Code/Cursor
def serve_http(orchestrator, *, host="127.0.0.1", port=8765, path="/mcp") -> None
    # blocking; ChatGPT developer-mode connectors
def http_app(orchestrator, *, host="127.0.0.1", path="/mcp", json_response=False) -> ASGIApp
    # the same endpoint as a plain ASGI app, bound to nothing — mount it inside your own
    # server behind your own TLS and auth, or build it to inspect without listening
def downscale_image(data: bytes, *, max_edge: int = 1024) -> bytes
SERVER_INFO: dict
```

### Connecting a client

```jsonc
// claude_desktop_config.json / Cursor MCP settings
{ "mcpServers": { "forge3d": {
    "command": "<python>", "args": ["-X", "utf8", "-m", "mcp_server"],
    "env": { "PYTHONPATH": "<repo>/src" } } } }
```

`python -m mcp_server` is the entry point (`__main__.py`): stdio by default, `--http` for a
streamable-HTTP connector, `--host/--port/--no-blender/--no-raw/--no-viewer` alongside.
`live_client_test.py` drives exactly this command with the SDK's own client.

## Layout

One file per responsibility:

| File | Owns |
|---|---|
| `registry.py` | `build_registry`, `tools_for` — collects content, partitions by role |
| `authorize.py` | who may call what, right now: the phase gate and the lease's grant |
| `context.py` | how a handler declared here reaches the live engine/orchestrator |
| `export_specs.py` | `export`'s two specs, re-issued with real handlers (ADR-014) |
| `session_specs.py` | the four session tools' declarations (Gate B 3.1) |
| `phase_tools.py` | `get_phase`, `promote_phase` handlers |
| `scene_query.py` | `list_objects`, `describe_object` handlers |
| `validation.py` | JSON-schema-shaped param validation against `ToolSpec.input_schema` |
| `serialize.py` | dataclass/`StrEnum`/tuple -> plain JSON-serialisable values |
| `dispatch.py` | `dispatch` — ties lookup, validation, authorisation, the lock and execution together |
| `images.py` | `downscale_image` |
| `transports.py` | `SERVER_INFO`, `serve_stdio`, `serve_http`, `http_app` — transport policy: identity, where it binds, the ADR-009 warning |
| `sdk_bridge.py` | the **only** file that touches the third-party `mcp` SDK: registry -> `tools/list`, `tools/call` -> `dispatch`, refusals -> error results |
| `__main__.py` | `python -m mcp_server` — the command a client launches |
| `conftest.py` | test-only — `FakeScene`/`orchestrator`/`write_lease` fixtures |

## Invariants

- **The role comes from the lease, never from the request** (ADR-013). `dispatch` ignores
  the `role` keyword entirely; `Orchestrator.authorize(tool_name, roles, lease)` decides, and
  a tool the lease does not hold or the phase does not permit raises
  `contracts.PhaseViolation`. Before this, `unwrap_uvs` (POLISH) and `add_railing` (REFINE)
  both ran in a session that had never left `blockout`.
- **This is not a security boundary.** ADR-009 gives every connected agent arbitrary code
  execution and full disk access by explicit user choice. Nothing here sandboxes, allowlists
  or AST-checks anything, and any doc implying otherwise is wrong.
- **A caller with no write lease reaches `INSPECT` tools and nothing else** — that is what
  lets any number of readers run beside the one writer (ADR-007).
- **`dispatch` never mutates without a live write lease.** A missing lease raises
  `contracts.ToolError`; a present-but-not-live one lets `contracts.LockContention` propagate
  from `orchestrator.verify` — both leave the scene untouched.
- **Every failure names a rule and a next step** (Gate A 4.2). Missing parameter -> the
  parameter and how to fix it. Wrong phase -> the phase, the roles legal in it, the phase the
  tool *would* be legal in, and `promote_phase`. Unknown tool -> the tools callable in this
  phase, not the whole catalogue. Unknown object -> how many objects exist and a sample of
  six ids, never all of them.
- **`raw_execute` is always recorded as an opaque undo barrier** when dispatched
  (`Operation(opaque=True)`) — ADR-009: rolling back past it needs a snapshot restore, not a
  replay, and that cost must stay visible in the log.
- **Export runs through its own handler, outside the operation log** (ADR-014). It produces
  no geometry, so a log entry for it is one undo could only treat as a no-op.
- **The HTTP transport binds loopback by default; a non-loopback bind logs a warning naming
  ADR-009** before the transport SDK is ever imported.
- **The registry and `dispatch` are fully usable whatever the SDK's state.** Only
  `serve_stdio`/`serve_http`/`http_app` need it, imported lazily inside the function body.
- **A refusal crosses the transport as an error *result*, never as an exception.** An
  exception escaping the SDK's `on_call_tool` reaches the client as an opaque JSON-RPC
  internal error with the rule, the detail and the suggestion all discarded — the exact
  opaque failure Gate A 4.2 was asked about. `sdk_bridge.call_tool` catches `RuleError` and
  returns `isError: true` carrying `{rule, detail, suggestion}`; anything that was *not* a
  `RuleError` still gets a rule (`mcp.unhandled_failure`) and never a traceback.
- **Every tool is declared to the client with its role and mutating flag** in `_meta`. A
  client has no other way to learn either, and both change what an agent should do before it
  calls.
- **Both transports run the same server object.** ADR-003 chose dual transport so a local
  editor and a consumer subscription get identical behaviour; two wirings would be two
  chances to drift.

## The tool-count budget (Gate B 3.3)

`contracts.ToolRole`'s own docstring puts the accuracy-optimal visible tool set at roughly
5-8, with degradation reported past ~10-15. Asked at Gate B 3.3 whether to split roles
further, hide tools, or exceed the band and measure it, the user chose **exceed it and
measure**: ship what is needed, record the real numbers, treat the band as guidance derived
from other systems rather than as law here.

Recorded counts, pinned by `registry_test.py::test_the_visible_tool_count_of_every_role_is_the_recorded_one`:

| Role | Tools | |
|---|---|---|
| `blockout` | 15 | includes texture create/update/apply |
| `refine` | 14 | includes texture create/update/apply |
| `repair` | 8 | |
| `align` | 7 | |
| `detail` | 7 | detail tools plus texture create/update/apply |
| `polish` | 5 | UV/bake tools plus texture create/update/apply |
| `inspect` | 11 | **over 8** — measurement, session, and texture discovery tools |
| `export` | 2 | |
| `admin` | 2 | |

**Several editing roles are over 8, deliberately (Gate B 3.3).** Crossing the
band is logged by `build_registry` every time it happens; it is never trimmed. That is the
change from the previous pass: a `_cap.py` used to round-robin each role down to eight, and
it silently hid `repair`, `make_plumb` and `close_visual_gap` — three core operations — from
every agent that would have called them, with every suite green. The real fix for `REFINE`'s
19 tools was splitting `REPAIR` and `ALIGN` out of it in `contracts.ToolRole`; capping was
the symptom. `_cap.py` is deleted.

If you add a tool and this table is wrong, update the table and the test. Updating it is the
measurement the decision asked for. Adding a cap so the number stops changing is not.

## The `mcp`/`mcp_server` package name collision — resolved

`pyproject.toml` lists `mcp` as a dependency — the official MCP Python SDK, imported as
`import mcp`. This package used to be called `mcp` too, and because the root `conftest.py`
puts `src/` first on `sys.path`, `import mcp` from anywhere in this codebase resolved to
*this* package and the SDK was permanently unreachable. **That is fixed**: the package was
renamed to `mcp_server`, the SDK is installed and importable in this environment (2.0.0),
and `transports_test.py::test_the_sdk_resolves_to_the_real_package_not_this_one` fails
immediately if the rename is ever undone. No gate decision is outstanding.

The SDK **version** gap is closed too. The transports were written against 1.x's low-level
decorator API (`Server.list_tools()` / `Server.call_tool()`), which 2.0.0 removed; they are
now wired against 2.0's `mcp.server.lowlevel.Server(on_list_tools=…, on_call_tool=…)`
constructor callbacks, in `sdk_bridge.py`. A real `mcp.client.session.ClientSession` connects
over a real stdio pipe and completes the whole journey — see `live_client_test.py`.

The callback seam is chosen over `MCPServer.add_tool` on purpose: `add_tool` derives a tool's
JSON Schema by introspecting a Python signature, and every `ToolSpec` here already carries a
hand-written schema with enums, `exclusiveMinimum` and `additionalProperties: false` that no
signature can express. The callbacks hand our schema through untouched.

## What this module deliberately does not do

- No sandbox, allowlist or AST check on `raw_execute` — that decision belongs to `raw`
  (ADR-009); this module routes the call through the write lock like any other mutating tool
  and marks it opaque.
- No real image codec (PNG/JPEG). `downscale_image` operates on binary PPM (`P6`) bytes —
  this codebase has no Pillow dependency; see `images.py`'s module docstring.
- No live-verified session against the SDK — see above.

## Dependencies

`contracts`, `ops`, `export`, `raw` at import time (real, constructed `ToolSpec` data).
`measure`, `gaps`, `align`, `uv`, `detail` imported defensively at registry-build time —
absence or a missing `*_SPECS` constant is not an error; `measure` again, inside
`describe_object`, for the per-object defect scan. `orchestration.Orchestrator` in tests only
(`conftest.py`). No `bpy`, ever.
