"""Tests for ``raw`` — unrestricted execution against the live engine (ADR-009).

This module was told explicitly not to sandbox, allowlist, or AST-check anything the user
supplies (Gate A 7.2, 7.4) — the risk is accepted, not mitigated, and no test below asks
for a security boundary that was deliberately not built. What these tests hold the module
to instead is **honesty**: that a script's effect on the scene is reported accurately
(``created``/``removed``/``objects_before``/``objects_after``), that a script which raises
produces a named ``error_rule`` rather than an unhandled traceback reaching the agent
(Gate A 4.2, and the wrapping ``contracts.RawOps.execute``'s own docstring requires of its
caller), that partial application is reported as what it is rather than papered over, and
that the risk statement (``describe_risk``) and the tool's role gating (``RAW_TOOL_SPEC``)
say plainly what this capability is.

``execute`` and ``describe_risk`` are throwing stubs as of this file (Rule 4 — tests come
first); most tests below are expected to fail with ``NotImplementedError`` until the next
pass implements them. ``RAW_TOOL_SPEC`` is real, already-constructed data — its tests pass
now, and must keep passing, because a regression there means a mutating tool reached the
read-only ``INSPECT`` role and broke the concurrency guarantee every other module depends
on (ADR-007).
"""

from __future__ import annotations

from contracts import ToolRole, Vec3
from raw import RAW_TOOL_SPEC, RawResult, describe_risk, execute
from testing import FakeEngine


# ------------------------------------------------------------------- effect on the scene

def test_a_creating_script_creates_the_object_and_names_it_in_created(
    engine: FakeEngine,
) -> None:
    """If the object were made but ``created`` did not name it, a caller reading the
    report has no way to know a new object exists at all; if ``created`` named an object
    that was never actually made, the caller trusts a scene state that does not exist.
    Either way, geometry is supposed to be derivable from what the report says happened."""
    result = execute(
        engine,
        "engine.create_primitive('box', 'cube', Vec3(1, 1, 1))",
        namespace={"Vec3": Vec3},
    )

    assert isinstance(result, RawResult)
    assert result.ok is True
    assert engine.exists("box")
    assert set(result.created) == {"box"}


def test_a_deleting_script_reports_the_object_in_removed(engine: FakeEngine) -> None:
    """A delete that succeeds in the engine but goes unreported in ``removed`` leaves a
    caller's model of the scene one object out of date — the exact drift the operation log
    exists to prevent (ADR-002)."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    result = execute(engine, "engine.delete('box')")

    assert result.ok is True
    assert not engine.exists("box")
    assert set(result.removed) == {"box"}


def test_objects_before_and_after_bracket_the_change_accurately(engine: FakeEngine) -> None:
    """``objects_before``/``objects_after`` are the raw material every other field is
    computed from. If they do not match the engine's actual state immediately before and
    after the call, ``created`` and ``removed`` are derived from wrong inputs and every
    downstream report is wrong in a way nothing else catches."""
    engine.create_primitive("keep", "cube", Vec3(1, 1, 1))
    before = tuple(engine.list_objects())

    result = execute(
        engine,
        "engine.create_primitive('new', 'cube', Vec3(1, 1, 1))\nengine.delete('keep')",
        namespace={"Vec3": Vec3},
    )

    after = tuple(engine.list_objects())
    assert result.objects_before == before
    assert result.objects_after == after
    assert "keep" in result.objects_before and "keep" not in result.objects_after
    assert "new" in result.objects_after and "new" not in result.objects_before


def test_returned_carries_only_plain_values_the_script_newly_bound(
    engine: FakeEngine,
) -> None:
    """``returned`` is what an agent actually reads to learn what its script computed. If
    it also carries the imported ``math`` module, the injected ``engine`` handle, a
    pre-seeded constant it never touched, or a function object, every raw call balloons at
    the token cost the docstring warns about and the one plain value the agent wanted —
    ``answer`` — gets lost in noise the agent still has to read past."""
    result = execute(
        engine,
        "import math\nanswer = 42\nscale = seed * 2\n\ndef helper():\n    return 1\n",
        namespace={"seed": 3},
    )

    assert result.ok is True
    assert result.returned == {"answer": 42, "scale": 6}


# --------------------------------------------------------------------------- error paths

def test_a_raising_script_returns_a_named_error_not_a_bare_traceback(
    engine: FakeEngine,
) -> None:
    """``contracts.RawOps.execute``'s own docstring says the caller must wrap every
    invocation because arbitrary code raises arbitrary exceptions; this module is that
    caller. An agent handed a bare traceback instead of a named rule loops on the same
    failing call — this is Gate A 4.2's exact failure mode, in the one place least able to
    predict what exception it will see."""
    result = execute(engine, "raise ValueError('boom')")

    assert result.ok is False
    assert result.error_rule == "raw.execution_failed"
    assert "ValueError" in result.error_detail


def test_a_syntactically_invalid_script_is_a_clean_failure_not_a_crash(
    engine: FakeEngine,
) -> None:
    """A ``SyntaxError`` surfaces at compile time, before ``exec`` runs a single line of
    the script — it is not a special case, but it is an easy one to miss when every other
    test exercises a script that at least parses. An agent that submits malformed Python
    must get the same named-error contract as one whose script raised at runtime, not an
    unhandled exception that kills the tool call."""
    result = execute(engine, "def broken(:\n    pass\n")

    assert result.ok is False
    assert result.error_rule == "raw.execution_failed"
    assert "SyntaxError" in result.error_detail


def test_a_script_that_raises_partway_through_keeps_what_it_already_created(
    engine: FakeEngine,
) -> None:
    """``exec`` runs statements in order against the live engine; a script that creates an
    object and then raises has genuinely created that object. A report that says
    ``ok=False`` and implies nothing happened is not a safe simplification — it is a
    report that does not match the scene, and the next call an agent makes (e.g. trying to
    create the same object again) will fail in a way the report gave it no reason to
    expect."""
    result = execute(
        engine,
        "engine.create_primitive('half', 'cube', Vec3(1, 1, 1))\nraise RuntimeError('stop')",
        namespace={"Vec3": Vec3},
    )

    assert result.ok is False
    assert engine.exists("half")
    assert "half" in result.created
    assert "half" in result.objects_after


def test_empty_or_whitespace_only_script_is_rejected_without_executing(
    engine: FakeEngine,
) -> None:
    """An empty script is not "a script that did nothing" — it is not a script at all, and
    running ``exec`` on it would be a silent no-op that still counts as a successful raw
    call. Rejecting it before ``engine.execute`` is ever reached is what
    ``engine.calls`` staying empty below proves: nothing in the engine was touched, not
    even a no-op execution."""
    result = execute(engine, "   \n\t\n  ")

    assert result.ok is False
    assert engine.calls == []


# ------------------------------------------------------------------------- risk honesty

def test_describe_risk_names_no_sandbox_and_no_filesystem_restriction() -> None:
    """ADR-009 is explicit that a security note which soft-pedals this capability is worse
    than none — a hedge like "use with caution" reads as reassurance to exactly the caller
    who most needs to understand there is no boundary at all. The text must say, in plain
    words, that there is no sandbox and no filesystem restriction, not merely mention the
    word "sandbox" in passing."""
    text = describe_risk()
    lowered = text.lower()

    assert (
        "no sandbox" in lowered or "not sandboxed" in lowered or "without a sandbox" in lowered
    ), "the text must deny a sandbox exists, not just mention the word"
    assert "filesystem" in lowered or "file system" in lowered, (
        "the text must name the unrestricted filesystem access ADR-009 also covers"
    )


# ------------------------------------------------------------------------ tool gating

def test_raw_tool_spec_is_admin_only_and_mutating() -> None:
    """If ``RAW_TOOL_SPEC`` were visible to any role but ``ADMIN``, or if ``mutating``
    were ``False``, raw execution would reach an agent that was never meant to hold it, or
    would run without taking the write lock every other mutation takes — either one turns
    the one capability with no security boundary into the one also missing the
    concurrency boundary."""
    assert RAW_TOOL_SPEC.roles == (ToolRole.ADMIN,)
    assert RAW_TOOL_SPEC.mutating is True


def test_raw_tool_spec_is_not_visible_to_the_inspect_role() -> None:
    """Many ``INSPECT`` agents run concurrently precisely because none of their tools can
    mutate (ADR-007). ``ToolSpec.__post_init__`` already refuses to construct a mutating
    tool scoped to ``INSPECT`` — this test is the guarantee that ``raw`` itself never tries
    to, since a regression here would mean this module stopped importing at all rather than
    quietly leaking the tool to a role that must never hold it."""
    assert ToolRole.INSPECT not in RAW_TOOL_SPEC.roles
