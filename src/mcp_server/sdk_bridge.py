"""The bridge onto the installed MCP SDK — the layer that makes this product reachable.

Everything else in ``mcp_server`` speaks in :class:`contracts.ToolSpec` and ``dispatch``.
Nothing else imports the third-party ``mcp`` package. This file is where those two meet,
which is why it is the only one that has to be re-read when the SDK changes shape.

**Which SDK surface, and why.** Installed here is ``mcp`` 2.0.0. It offers two ways to
declare tools:

``mcp.server.MCPServer.add_tool(fn)``
    Derives each tool's JSON Schema by introspecting a Python function signature. Wrong
    for this product: every ``ToolSpec`` already carries a hand-written schema with
    enums, ``exclusiveMinimum`` and ``additionalProperties: False``, none of which a
    signature can express. Going through ``add_tool`` would mean generating functions and
    then hoping the schema it inferred matched the one we wrote.

``mcp.server.lowlevel.Server(..., on_list_tools=, on_call_tool=)``
    Two async callbacks; our schema passes through untouched. This is what is used.

The 1.x ``Server.list_tools()`` / ``Server.call_tool()`` **decorators** are gone in 2.0 —
verified against the installed package, not from memory, and that removal is exactly what
had left both transports unable to serve anything.

**What crosses the boundary in each direction.** Outbound: every registered tool, with its
role and mutating flag in ``_meta`` so a client can reason about a tool before being refused
by it. Inbound: a tool name and arguments, which go straight to ``dispatch`` — validation,
authorisation, the write lock and execution are its business and are not re-implemented
here. What *is* decided here is the one thing ``dispatch`` cannot know: that a live session
is a single logical writer (see :data:`LEASE_HOLDER`), and that a refusal must come back as
an error **result** rather than an exception (see :func:`call_tool`).
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable

from contracts import RuleError, ToolSpec

from .dispatch import dispatch
from .registry import build_registry
from .validation import validate_params

__all__ = ["LEASE_HOLDER", "SdkModules", "load_sdk", "tool_specs", "sdk_tools", "call_tool", "build_server"]

_LOG = logging.getLogger(__name__)

LEASE_HOLDER = "mcp-session"
"""One logical writer per server process.

MCP has no native notion of a role or a lease, so a connected client is treated as a single
writer that keeps renewing its own. Same-holder re-acquire renews rather than contends
(``orchestration.LockingMixin.acquire``), so a client can make more than one change per
connection; a second *process* still contends properly, which is ADR-007's actual guarantee.
The limits of that model are stated in this module's ``CLAUDE.md`` and are real.
"""

_SDK_MISSING = (
    "the `mcp` Python SDK is not importable (pip install mcp) — {transport} needs it to "
    "actually speak the protocol. The tool registry and dispatch() work without it; only "
    "serving a live connection over {transport} does not."
)

_SDK_INCOMPATIBLE = (
    "the installed `mcp` SDK's `mcp.server.Server` does not accept the `on_list_tools` / "
    "`on_call_tool` constructor callbacks this module wires against (SDK 2.0). Installed "
    "here: {version}. Refusing to serve rather than failing with an AttributeError or a "
    "TypeError from inside the SDK, which would not say which side is wrong. If the SDK "
    "has moved again, re-read `mcp.server.lowlevel.server` and rewire `build_server` — "
    "that is the only function in this product that touches the SDK's tool API."
)

_UNHANDLED = (
    "this is a defect in forge3d, not in your call: the tool exists and your parameters "
    "passed validation. Call get_phase() to re-orient and try a different route; if it "
    "repeats, report it with the rule name above."
)


@dataclass(frozen=True)
class SdkModules:
    """The three SDK modules this product uses, resolved once and passed around explicitly.

    Explicit rather than imported at module scope for two reasons. The registry and
    ``dispatch`` must stay fully usable on a machine with no SDK installed — that is most
    of the test suite — and a test needs to be able to hand in a deliberately wrong SDK to
    prove the version guard actually guards (``sdk_bridge_test``).
    """

    server: Any
    types: Any
    stdio: Any
    transport: str


def load_sdk(transport: str) -> SdkModules:
    """Import the SDK lazily and name the failure if it is absent.

    ``importlib.import_module`` rather than a bare ``import mcp.server``: it returns
    whatever is in ``sys.modules`` for that name, so a test can substitute one. A plain
    ``import mcp.server; return mcp.server`` reads the attribute off the parent package
    instead and silently ignores the substitution.

    This package used to be *called* ``mcp``, which is the SDK's own import name, so
    ``import mcp`` from inside it resolved back here and the SDK was permanently
    unreachable — no subscription client could ever have connected, the one thing Gate A
    7.4 asked for. The rename fixed it and ``transports_test`` pins the fix.
    """
    try:
        return SdkModules(
            server=importlib.import_module("mcp.server"),
            types=importlib.import_module("mcp.types"),
            stdio=importlib.import_module("mcp.server.stdio"),
            transport=transport,
        )
    except ImportError as exc:
        raise RuntimeError(_SDK_MISSING.format(transport=transport)) from exc


def _sdk_version() -> str:
    try:
        import importlib.metadata as metadata

        return metadata.version("mcp")
    except Exception:  # noqa: BLE001 — a missing version must not mask the real error
        return "unknown"


def tool_specs() -> dict[str, ToolSpec]:
    """Every registered tool, by name, across every role.

    Flattened deliberately: MCP has one flat tool namespace per connection, and *which*
    role may call a tool is decided per call from the lease (ADR-013), not by hiding it at
    listing time. Hiding is also what ``_cap.py`` did before Gate B 3.3 deleted it, and it
    made three core operations invisible to every agent with the whole suite green.
    """
    return {spec.name: spec for specs in build_registry().values() for spec in specs}


def sdk_tools(sdk: SdkModules, specs: Iterable[ToolSpec]) -> list[Any]:
    """Our specs as the SDK's wire type, schema and all.

    ``_meta`` carries the role and the mutating flag because a client has no other way to
    learn them, and both change what an agent should do *before* it calls: the role says
    which phase a tool belongs to, and the flag says whether the call needs the write lock.
    """
    types_ = sdk.types
    return [
        types_.Tool(
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_schema,
            annotations=types_.ToolAnnotations(
                read_only_hint=not spec.mutating,
                destructive_hint=spec.mutating,
            ),
            meta={
                "roles": [role.value for role in spec.roles],
                "mutating": spec.mutating,
                "examples": list(spec.examples),
            },
        )
        for spec in specs
    ]


def _result(sdk: SdkModules, payload: Any, *, is_error: bool = False) -> Any:
    """One answer in both shapes the ecosystem reads: ``content`` for clients that render
    text to a person, ``structuredContent`` for clients that parse it for a model. Sending
    only one leaves half of them showing nothing."""
    types_ = sdk.types
    structured = payload if isinstance(payload, dict) else {"result": payload}
    return types_.CallToolResult(
        content=[types_.TextContent(type="text", text=json.dumps(payload, indent=2, default=str))],
        structured_content=structured,
        is_error=is_error,
    )


def _refusal(sdk: SdkModules, error: RuleError) -> Any:
    """A named rule and a next step, as an error *result*.

    Gate A 4.2, verbatim: the agent is told which rule broke. An exception allowed to
    escape ``on_call_tool`` reaches the client as an opaque JSON-RPC internal error with
    the rule, the detail and the suggestion all discarded — which is precisely the opaque
    failure that makes an agent retry the same call forever.
    """
    payload = error.as_dict()
    text = f"{payload['rule']}: {payload['detail']}"
    if payload["suggestion"]:
        text += f"\nNext step: {payload['suggestion']}"
    types_ = sdk.types
    return types_.CallToolResult(
        content=[types_.TextContent(type="text", text=text)],
        structured_content=payload,
        is_error=True,
    )


def _unhandled(sdk: SdkModules, name: str, exc: Exception) -> Any:
    """Anything that was not a ``RuleError``. Still named, still actionable, and still not
    a traceback — a stack trace names our files and none of the agent's options."""
    _LOG.exception("mcp tool %r failed with an unnamed error", name)
    return _refusal(
        sdk,
        RuleError(
            rule="mcp.unhandled_failure",
            detail=f"{name!r} failed with {type(exc).__name__}: {exc}",
            suggestion=_UNHANDLED,
        ),
    )


def call_tool(
    sdk: SdkModules,
    name: str,
    arguments: dict[str, Any],
    *,
    specs: dict[str, ToolSpec],
    orchestrator: Any,
) -> Any:
    """Route one ``tools/call`` and turn every outcome into a result the client can read.

    The lease is the only policy decided here. A read-only tool takes none at all, which is
    what lets many INSPECT agents run beside the one writer (ADR-007). A mutating tool
    acquires under :data:`LEASE_HOLDER`; the transport passed *no* lease before this module
    existed, so every mutating call over a live connection was refused with
    ``mcp.lock_required``.

    Parameters are validated **before** the lease is acquired, mirroring ``dispatch``'s own
    deliberate order rather than undoing it one layer up. Acquiring first would mean a
    misspelled tool name or a bad enum value takes the write lock away from whoever is
    actually building, for a call that was never going to run. ``validate_params`` is the
    same pure function ``dispatch`` calls again a moment later, so there are two runs of one
    rule here, never two rules.
    """
    try:
        spec = specs.get(name)
        lease = None
        if spec is not None and spec.mutating:
            validate_params(name, spec.input_schema, arguments)
            lease = orchestrator.acquire(LEASE_HOLDER, orchestrator.phase)
        return _result(sdk, dispatch(name, arguments, orchestrator=orchestrator, lease=lease))
    except RuleError as refused:
        return _refusal(sdk, refused)
    except Exception as exc:  # noqa: BLE001 — an unnamed failure must still name a rule
        return _unhandled(sdk, name, exc)


def _accepts_callbacks(server_class: Any) -> bool:
    try:
        parameters = inspect.signature(server_class.__init__).parameters
    except (TypeError, ValueError):
        return False
    return "on_list_tools" in parameters and "on_call_tool" in parameters


def build_server(sdk: SdkModules, orchestrator: Any, *, name: str, version: str) -> Any:
    """The SDK server object, with this product's whole tool catalogue behind it.

    Both transports run the same object — ADR-003 chose dual transport so that a local
    editor and a consumer subscription reach identical behaviour, and two wirings would be
    two chances for them to drift.

    The catalogue is collected **once**, at build time, rather than per request: every
    source it collects from is static, constructed data, and rebuilding it inside
    ``tools/list`` would re-import five optional sibling modules on every keystroke of a
    client that lists eagerly.
    """
    server_class = getattr(sdk.server, "Server", None)
    if server_class is None or not _accepts_callbacks(server_class):
        raise RuntimeError(_SDK_INCOMPATIBLE.format(version=_sdk_version()))

    specs = tool_specs()
    declared = sdk_tools(sdk, specs.values())

    async def on_list_tools(_ctx: Any, _params: Any) -> Any:
        return sdk.types.ListToolsResult(tools=declared)

    async def on_call_tool(_ctx: Any, params: Any) -> Any:
        return call_tool(
            sdk, params.name, dict(params.arguments or {}),
            specs=specs, orchestrator=orchestrator,
        )

    return server_class(
        name,
        version=version,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
