# mcp_server

The MCP server: registry policy, dispatch, both transports, image downscaling (ADR-003).
This is the module through which everything the rest of the product builds becomes
reachable by a connected agent. Gate A 7.4, verbatim: *"also make sure it supports my
subscriptions eg: chatgpt subscription so that i can use it with it."* MCP is the only
path where a consumer subscription drives the tool with no per-token billing layered on
top, which is why both transports exist: **stdio** for Claude Desktop / Claude Code /
Cursor, **streamable HTTP** for ChatGPT developer-mode connectors.

Registry **content** — what a tool does — is declared beside each operation
(`ops.OP_SPECS`, `export.EXPORT_SPECS`, `raw.RAW_TOOL_SPEC`, and whatever
`measure`/`gaps`/`align`/`uv`/`detail` publish under a `*_SPECS` constant). Registry
**policy** — which of the seven `contracts.ToolRole` values sees which handful of tools,
how a call is validated and locked, how an oversized render gets downscaled before it
costs 15-25k tokens instead of ~1,600 — lives here.

## Public interface

Everything importable from `mcp_server` is declared in `mcp_server/__init__.py`:

```python
def build_registry(*, include_raw: bool = True) -> dict[ToolRole, tuple[ToolSpec, ...]]
    # collects OP_SPECS, EXPORT_SPECS, RAW_TOOL_SPEC, and measure/gaps/align/uv/detail's
    # *_SPECS constants where they exist, partitions by role, and caps each role's slice
    # at 8 tools (see "The REFINE-role cap" below)

def tools_for(role: ToolRole) -> tuple[ToolSpec, ...]
    # role's slice of the default registry (include_raw=True)

def dispatch(name: str, params: dict, *, role: ToolRole, orchestrator, lease=None) -> dict
    # role visibility -> param validation -> write lock (mutating only) -> execute ->
    # JSON-serialisable result

def serve_stdio(orchestrator) -> None       # blocking; Claude Desktop/Code/Cursor
def serve_http(orchestrator, *, host="127.0.0.1", port=8765) -> object   # ChatGPT connectors
def downscale_image(data: bytes, *, max_edge: int = 1024) -> bytes
SERVER_INFO: dict
```

## Layout

One file per responsibility:

| File | Owns |
|---|---|
| `registry.py` | `build_registry`, `tools_for` — collects content, applies the per-role cap |
| `_cap.py` | the fair round-robin cap that keeps a role's visible set within ADR-003's bound |
| `validation.py` | JSON-schema-shaped param validation against `ToolSpec.input_schema` |
| `serialize.py` | dataclass/`StrEnum`/tuple -> plain JSON-serialisable values |
| `dispatch.py` | `dispatch` — ties visibility, validation, the write lock and execution together |
| `images.py` | `downscale_image` |
| `transports.py` | `SERVER_INFO`, `serve_stdio`, `serve_http` |
| `conftest.py` | test-only — `FakeScene`/`orchestrator`/`write_lease` fixtures |

## Invariants

- **Every role's visible tool set is 1-8 tools**, the whole catalogue is bigger than any
  single role's slice, and no `ToolRole.INSPECT` tool is mutating (ADR-003, ADR-007).
- **`dispatch` never mutates without a live write lease.** A missing lease raises
  `contracts.ToolError`; a present-but-not-live one lets `contracts.LockContention`
  propagate from `orchestrator.verify` — both leave `orchestrator`'s scene untouched.
- **Every failure names what's wrong.** Wrong role -> the role. Missing parameter -> the
  parameter, plus a `suggestion`. No handler wired -> a named `ToolError`, never a bare
  `TypeError` from calling `None(...)`. Gate A 4.2: an agent handed a bare traceback loops
  on the same failing call; one told what's wrong fixes it first try.
- **`raw_execute` is always recorded as an opaque undo barrier** when dispatched
  (`Operation(opaque=True)`) — ADR-009: rolling back past it needs a snapshot restore, not
  a replay, and that cost must stay visible in the log.
- **The HTTP transport binds loopback by default; a non-loopback bind logs a warning
  naming ADR-009** before the transport SDK is ever imported, so it fires even when the
  SDK is absent.
- **The registry and `dispatch` are fully usable without the `mcp_server` Python SDK installed.**
  Only `serve_stdio`/`serve_http` need it, imported lazily inside the function body; its
  absence raises one clear `RuntimeError`, never a bare `ModuleNotFoundError` from three
  frames inside someone else's package.

## The REFINE-role cap

`contracts.ToolRole`'s own docstring puts the accuracy-optimal visible-tool-set bound at
2-7, hard-capped at 8 here. `ops`, `gaps` and `align` each independently, correctly declare
some or all of their tools under `ToolRole.REFINE` (`Phase.REFINE`'s own docstring: "correct
topology, close gaps, resolve clipping, fix alignment" — all three genuinely belong there).
Combined, that is 4 + 8 + 7 = 19 tools in one role as of this writing — nothing in any one
module is wrong, and nothing enforced the *combined* total across modules built in parallel
by separate agents (Rule 5).

`build_registry` enforces the bound itself (`_cap.py`): it round-robins one tool at a time
across each contributing source, in a fixed source order, until the cap is reached, rather
than taking the first 8 in source-priority order — the latter would zero out whichever
source happens to be declared last (`align`, in the current source order) entirely. Excluded
tools are logged once, by name and source, and are not deleted anywhere — they remain fully
present in `gaps.GAPS_SPECS`/`align.ALIGN_SPECS` themselves, just not all simultaneously
visible through `mcp_server`'s default REFINE slice.

This is a stopgap, not a resolution. Recorded as a real finding (see this task's
`assumptions` output) with three candidate real fixes, none of which this module can make
unilaterally (Rule 5 — `src/contracts/`, `src/gaps/`, `src/align/` are outside its write
boundary):

1. `contracts.ToolRole` gains finer granularity than one flat `REFINE` bucket.
2. `gaps`/`align` consolidate their fine-grained tools into fewer umbrella ones — `gaps`'s
   own `repair` tool ("run every applicable repair tier … re-measuring between tiers") is
   already exactly this pattern for six of its eight tools.
3. Tool visibility is chosen per session/sub-agent rather than statically per `ToolRole`.

## The `mcp_server` package name collision

`pyproject.toml` already lists `mcp>=1.2.0` as a real dependency — the official MCP Python
SDK, imported by users as `import mcp`. This package *is* `src/mcp_server/`, imported the same way.
Because the root `conftest.py` puts `src/` first on `sys.path`, `import mcp` from anywhere
in this codebase — including from inside this very package's own `transports.py` —resolves
to **this** package (already cached in `sys.modules` under that name), never the installed
SDK, regardless of install order. `serve_stdio`/`serve_http`'s lazy `import mcp.server` is
written the way it will need to work once this is resolved, but cannot fix it from inside
`src/mcp_server/` — see `transports.py`'s module docstring and this task's `assumptions` output for
the two ways out (alias the SDK into `sys.modules` under another name before importing this
package at process start, or rename this package).

## What this module deliberately does not do

- No sandbox, allowlist or AST check on `raw_execute` — that decision belongs to `raw`
  (ADR-009); this module only routes the call through the write lock like any other
  mutating tool and marks it opaque.
- No real image codec (PNG/JPEG). `downscale_image` operates on binary PPM (`P6`) bytes —
  this codebase has no Pillow dependency; see `images.py`'s module docstring.
- No live, verified wiring against the `mcp_server` Python SDK — it is not installed in this
  environment (nor, per the name collision above, cleanly importable from inside this
  package yet). `serve_stdio`/`serve_http`'s SDK-present code paths are best-effort and
  explicitly flagged as unverified in their own docstrings.

## Dependencies

`contracts`, `ops`, `export`, `raw` at import time (real, constructed `ToolSpec` data).
`measure`, `gaps`, `align`, `uv`, `detail` imported defensively at registry-build time —
absence or a missing `*_SPECS` constant is not an error. `orchestration.Orchestrator` in
tests only (`conftest.py`). No `bpy`, ever.
