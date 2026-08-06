"""``raw.execute`` and ``describe_risk`` — throwing stubs; ``RAW_TOOL_SPEC`` — real data.

``execute`` is the wrapper ``contracts.RawOps.execute``'s own docstring requires: arbitrary
code raises arbitrary exceptions, so *something* has to catch them and hand back a named
rule instead of a bare traceback, or Gate A 4.2 is broken for exactly the one tool where it
matters most. This file is that something — once implemented.

For now every function body raises ``NotImplementedError("raw.<name>: not implemented")``
(Rule 4 — tests come first). This file exists so ``raw_test.py`` imports a real module with
the right shape — signatures, docstrings, the constructed ``RAW_TOOL_SPEC`` — and fails on
an assertion or on this explicit error, never on ``ImportError`` or ``AttributeError``. The
implementer's only job is to replace these two bodies until
``python -m pytest src/raw`` is green; the signatures, ``RawResult``'s fields and
``RAW_TOOL_SPEC`` are the contract and do not move.

``RAW_TOOL_SPEC`` is deliberately NOT a stub. It is real, constructed data, because
``contracts.ToolSpec.__post_init__`` runs a contract check at construction time — a
mutating tool may never be handed to the read-only ``INSPECT`` role (ADR-007) — and that
check has to run, and pass, the moment this module is imported. Getting it wrong here would
mean the one module built around an already-accepted security trade-off (ADR-009) is also
the module that breaks the concurrency guarantee every other module depends on.
"""

from __future__ import annotations

import types
from dataclasses import dataclass

from contracts import EngineProtocol, ToolRole, ToolSpec

__all__ = ["RawResult", "execute", "describe_risk", "RAW_TOOL_SPEC"]

_NOT_IMPLEMENTED = "raw.{name}: not implemented"


@dataclass(frozen=True)
class RawResult:
    """What one raw call reports back.

    Shaped like every other module's result type (``contracts.OperationResult``,
    ``contracts.ActionReport``) on purpose — an agent that just ran arbitrary code still
    gets "what changed" in the same shape as any other tool call, plus the one thing raw
    execution uniquely risks: an unhandled exception, named rather than left as a
    traceback.

    ``created`` and ``removed`` are computed from ``objects_before``/``objects_after``, not
    trusted from anything the script claims about itself — a script cannot self-report
    objects it never actually created.

    ``returned`` holds only plain, non-callable, non-module names the script itself bound
    during execution. Names that were already in scope before the script ran (the injected
    ``engine`` handle, anything the caller pre-seeded via ``namespace``) are not "bound by
    the script" and are excluded, same as any imported module or defined function — none of
    them are the kind of small, inspectable value a report should spend tokens echoing
    back.
    """

    ok: bool
    objects_before: tuple[str, ...]
    objects_after: tuple[str, ...]
    created: tuple[str, ...]
    removed: tuple[str, ...]
    returned: dict
    error_rule: str = ""
    error_detail: str = ""


def execute(engine: EngineProtocol, source: str, *, namespace: dict | None = None) -> RawResult:
    """Run ``source`` against ``engine`` and report what happened — honestly, and without
    ever raising for a failure *inside* ``source``.

    Once implemented, this function must:

    - Reject an empty or whitespace-only ``source`` with ``ok=False`` before calling
      ``engine.execute`` at all — there is nothing to run, and "ran nothing" must not be
      reported as if a script executed.
    - Record ``objects_before``/``objects_after`` from ``engine.list_objects()`` taken
      immediately before and after the call, and derive ``created``/``removed`` from their
      difference — never from anything the script itself reports.
    - Catch every exception ``engine.execute`` can raise — including a ``SyntaxError`` from
      malformed ``source``, which surfaces at compile time, before a single line runs — and
      turn it into ``ok=False``, ``error_rule="raw.execution_failed"``, and an
      ``error_detail`` that names the exception type. This is the wrapping
      ``contracts.RawOps.execute``'s docstring requires verbatim; not wrapping it is how an
      agent ends up looping on a traceback it cannot act on.
    - Leave in place whatever the script already did before it raised. A script that
      creates three objects and then raises on the fourth has genuinely created three
      objects — ``created`` must name them and ``objects_after`` must include them, even
      though ``ok`` is ``False``. Reporting "nothing happened" about a partly-applied
      script is a report that does not match the scene.
    - Filter ``returned`` to plain values the script newly bound: no modules, no callables,
      and nothing that was already present in the namespace before ``source`` ran (the
      injected ``engine`` handle included).

    What this function must NOT do, per ADR-009 and this module's own boundary: add an
    allowlist, an AST check, or any other narrowing of what ``source`` may contain. The
    absence of a sandbox here is a decision already made, not a gap this function closes.

    Taking the write lock and recording the call as an opaque undo barrier
    (``contracts.SceneDocument.append`` with ``opaque=True``) is deliberately NOT this
    function's job — there is no ``SceneDocument``/``WriteLease`` in this signature. This
    module depends only on ``contracts`` (see ``.pipeline/modules.json``); the module that
    already owns the write lock and the operation log applies that machinery around every
    call to this one, using ``RAW_TOOL_SPEC.mutating`` to know it must.
    """
    if not source or not source.strip():
        return RawResult(
            ok=False,
            objects_before=(),
            objects_after=(),
            created=(),
            removed=(),
            returned={},
            error_rule="raw.empty_script",
            error_detail="source is empty or whitespace-only; nothing was executed",
        )

    # Names already in scope before `source` runs — the injected `engine` handle and
    # anything the caller pre-seeded — are not "bound by the script" and are excluded
    # from `returned` below, however the run turns out.
    pre_existing = set(namespace or {}) | {"engine"}

    objects_before = tuple(engine.list_objects())
    ns: dict | None = None
    ok = True
    error_rule = ""
    error_detail = ""
    try:
        ns = engine.execute(source, namespace)
    except Exception as exc:  # noqa: BLE001 — arbitrary code raises arbitrary exceptions
        ok = False
        error_rule = "raw.execution_failed"
        error_detail = f"{type(exc).__name__}: {exc}"
    objects_after = tuple(engine.list_objects())

    created = tuple(oid for oid in objects_after if oid not in objects_before)
    removed = tuple(oid for oid in objects_before if oid not in objects_after)

    returned: dict = {}
    if ns is not None:
        for key, value in ns.items():
            if key in pre_existing:
                continue
            if key.startswith("__") and key.endswith("__"):
                continue
            if isinstance(value, types.ModuleType):
                continue
            if callable(value):
                continue
            returned[key] = value

    return RawResult(
        ok=ok,
        objects_before=objects_before,
        objects_after=objects_after,
        created=created,
        removed=removed,
        returned=returned,
        error_rule=error_rule,
        error_detail=error_detail,
    )


def describe_risk() -> str:
    """The exact text shown to a caller before first use.

    Must name the exposure plainly and in these terms specifically: **no sandbox** and
    **no filesystem restriction**. ADR-009 is explicit that a security note which
    soft-pedals this — "use with caution", "be careful with untrusted input" — is worse
    than no note at all, because it reads as reassurance to exactly the caller who most
    needs to understand there is none.
    """
    return (
        "raw execution runs arbitrary Python against the live engine with no sandbox and "
        "no allowlist — there is no security boundary of any kind. It also places no "
        "restriction on which filesystem paths a script may read or write: a script run "
        "through this tool can read, write, or delete anything on the filesystem that the "
        "user running this process can. This is unrestricted code execution on the user's "
        "own machine (ADR-009), not a sandboxed or otherwise contained capability."
    )


RAW_TOOL_SPEC = ToolSpec(
    name="raw_execute",
    description=(
        "Run arbitrary Python against the live engine, with `engine` bound in scope. "
        "No sandbox, no allowlist, no filesystem restriction (ADR-009) — this is "
        "unrestricted code execution on the user's own machine. Every call is recorded "
        "as an opaque undo barrier: rolling back past it needs a snapshot restore, not a "
        "replay. Admin role only."
    ),
    roles=(ToolRole.ADMIN,),
    input_schema={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "Python source executed with `engine` bound to the live "
                    "EngineProtocol implementation."
                ),
            },
        },
        "required": ["source"],
        "additionalProperties": False,
    },
    mutating=True,
    examples=("engine.create_primitive('post', 'cube', Vec3(0.1, 0.1, 1.0))",),
)
