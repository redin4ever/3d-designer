# raw

Unrestricted Python execution against the live engine. A connected agent can run any
script it wants, with `engine` — the live `EngineProtocol` implementation — bound in
scope. This module owns exactly two functions and one MCP tool declaration over
`EngineProtocol`; it never imports `bpy`, and is testable end to end against `FakeEngine`
like every module outside `src/engine/` (ADR-008).

## The exposure

**There is no sandbox, no allowlist, and no restriction on which filesystem paths a
script may read or write.** A script run through this module can do anything the user
running the process can do. This is the same design the de-facto standard agent-Blender
bridge uses, and it carries an open CVSS 9.0 remote-code-execution issue as a result. It
was chosen anyway, explicitly, with that precedent named in the question — see
[`docs/adr/ADR-009-unrestricted-execution-local-trust.md`](../../docs/adr/ADR-009-unrestricted-execution-local-trust.md)
for the decision and the trust boundary (a single user's own machine) that makes it
acceptable here. `describe_risk()` returns this same statement for display to a caller
before first use; it is written once, in `executor.py`, and referenced rather than
repeated elsewhere in this codebase.

## Public interface

Everything importable from `raw` is re-exported by `__init__.py`:

```python
@dataclass(frozen=True)
class RawResult:
    ok: bool
    objects_before: tuple[str, ...]   # engine.list_objects() immediately before the call
    objects_after: tuple[str, ...]    # engine.list_objects() immediately after
    created: tuple[str, ...]          # objects_after - objects_before
    removed: tuple[str, ...]          # objects_before - objects_after
    returned: dict                    # plain values the script newly bound; no modules,
                                       # no callables, nothing pre-existing in scope
    error_rule: str = ""              # "raw.execution_failed" when ok is False
    error_detail: str = ""            # names the exception type, never a bare traceback

def execute(engine: EngineProtocol, source: str, *, namespace: dict | None = None) -> RawResult: ...
    # Runs `source`, reports what changed. Never raises for a failure inside `source` —
    # it is the wrapper contracts.RawOps.execute's own docstring requires of its caller.

def describe_risk() -> str: ...
    # The exact text shown to a caller before first use. See "The exposure" above.

RAW_TOOL_SPEC: ToolSpec
    # roles=(ToolRole.ADMIN,), mutating=True. Real, constructed data — not a stub — because
    # ToolSpec.__post_init__ enforces at construction time that a mutating tool is never
    # exposed to the read-only INSPECT role (ADR-007), and that check must pass at import.
```

## Invariants

What `raw_test.py` checks, and what any future change must keep true:

1. **`created`/`removed` are derived, never self-reported.** They come from the actual
   difference between `objects_before` and `objects_after`, not from anything the script
   claims about itself.
2. **A raising script never reaches the caller as a bare traceback.** It comes back as
   `RawResult(ok=False, error_rule="raw.execution_failed", error_detail=...)`, with
   `error_detail` naming the exception type. This includes a `SyntaxError` from malformed
   `source` — a compile-time failure, not a runtime one, but still a failure this module
   must catch rather than let propagate.
3. **Partial application is reported as what it is.** A script that creates objects and
   then raises has genuinely created those objects; `created` and `objects_after` include
   them even though `ok` is `False`. Nothing here rolls anything back.
4. **`returned` excludes modules and callables, and anything not newly bound by the
   script.** The injected `engine` handle, an imported module, a defined function, and
   anything pre-seeded via the `namespace` argument are all excluded — none of them are
   the small, inspectable value an agent asked for.
5. **An empty or whitespace-only script is rejected before `engine.execute` runs at
   all.** "Ran nothing" is not a successful execution.
6. **`RAW_TOOL_SPEC` is admin-only and mutating, and never visible to `INSPECT`.** Many
   `INSPECT` agents run concurrently precisely because none of their tools mutate
   (ADR-007); this is the one tool in the whole registry where getting that wrong would
   hand unrestricted code execution to a role meant to be read-only.

## What this module deliberately does not do

No sandbox, no allowlist, no AST check, no path restriction. This is not an oversight —
adding any of those would silently narrow a capability the user chose explicitly with the
risk named, and that decision belongs at a gate, not inside this module. See ADR-009.

Taking the write lock and recording each call as an opaque undo barrier
(`contracts.SceneDocument.append(..., opaque=True)`) is also not this module's job —
`execute()` takes no `SceneDocument`/`WriteLease`. That machinery is owned by the module
that already holds it (see `dependsOn` in `.pipeline/modules.json`); this module only
marks itself `mutating=True` so that machinery knows to apply it.

## Dependencies

- `src/contracts/` for `EngineProtocol`, `ToolSpec`, `ToolRole` (frozen surface — never
  edited from here; see `.pipeline/contract-requests.json` for anything missing).
- `src/testing/` (`FakeEngine`, via the root `engine` fixture) in tests only.
- No `bpy`, ever.
