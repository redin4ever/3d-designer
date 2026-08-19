"""Tests for role-and-phase authorisation on the ``dispatch`` path (ADR-013, Gate B 6.3).

Before this file existed, ``dispatch`` checked only that the requested tool was visible to
the role string **the caller itself passed with the call**, and never compared that to the
session's phase. Verified live against the real product: ``unwrap_uvs`` (POLISH) and
``add_railing`` (REFINE) both succeeded while the session had never left ``blockout``, and
any agent could hold any role simply by naming it. Every test here is one half of closing
that: the role comes from the lease, and the phase is checked.
"""

from __future__ import annotations

import dataclasses

import pytest
from contracts import Phase, PhaseViolation, ToolRole, Vec3
from mcp_server import dispatch

_PRIMITIVE = {"object_id": "box1", "kind": "cube", "size": [1, 1, 1]}


def _narrow(fake_scene, lease, roles: tuple[ToolRole, ...]):
    """Re-issue the live lease with a narrowed role grant.

    ``Orchestrator.acquire`` does not yet accept ``roles`` (``contracts.WriteLockManager``
    declares it; ``orchestration/locking.py`` has not implemented it this round), so a
    multi-agent grant is set up by replacing the one field the lock is held in. The lease
    stays the live one, which is the property that matters — a lease a caller builds for
    itself proves nothing.
    """
    narrowed = dataclasses.replace(lease, roles=roles)
    fake_scene.document.active_lease = narrowed
    return narrowed


# ------------------------------------------------------------- the phase is enforced

def test_a_polish_tool_is_refused_while_the_session_is_still_in_blockout(
    orchestrator, write_lease, fake_scene,
) -> None:
    """The measured defect this whole item exists for: ``unwrap_uvs`` ran to completion in
    a session that had never left ``blockout``. If this passes silently, the staged plan
    the user chose at Gate A 3.2 constrains nothing at all — an agent can UV-unwrap boxes
    whose proportions are not settled, and the product's central claim (professional
    progression, not glued primitives) is decoration."""
    with pytest.raises(PhaseViolation):
        dispatch(
            "unwrap_uvs", {"object_id": "box1"},
            role=ToolRole.POLISH, orchestrator=orchestrator, lease=write_lease,
        )
    assert fake_scene.document.head == 0


def test_a_refine_tool_is_refused_in_blockout_too(orchestrator, write_lease) -> None:
    """The second half of the same live finding: ``add_railing`` (REFINE) also succeeded
    in ``blockout``. Detailing geometry whose shape is not settled is the exact ordering
    this refuses."""
    with pytest.raises(PhaseViolation):
        dispatch(
            "add_railing",
            {
                "object_id": "rail", "path": [[0, 0, 0], [1, 0, 0]],
                "height": 0.95, "post_spacing": 1.0, "baluster_gap": 0.09,
            },
            role=ToolRole.REFINE, orchestrator=orchestrator, lease=write_lease,
        )


def test_the_same_polish_tool_is_accepted_once_the_session_reaches_polish(
    orchestrator, fake_scene,
) -> None:
    """A gate that never opens is a wall. If promotion does not actually widen what an
    agent may call, an autonomous run can never finish the work it was asked to do."""
    fake_scene.document.phase = Phase.POLISH
    lease = orchestrator.acquire(holder="w", phase=Phase.POLISH)
    fake_scene.engine.create_primitive("box1", "cube", Vec3(1.0, 1.0, 1.0))

    result = dispatch(
        "unwrap_uvs", {"object_id": "box1"},
        role=ToolRole.POLISH, orchestrator=orchestrator, lease=lease,
    )
    assert result["ok"] is True


# ------------------------------------------------- the caller's claimed role is ignored

def test_the_role_the_caller_declares_cannot_widen_what_it_may_call(
    orchestrator, write_lease,
) -> None:
    """Any agent could claim any role by passing it. The declared role must have no
    authority whatsoever — a POLISH claim from a blockout-phase session is still refused,
    or the check is theatre."""
    with pytest.raises(PhaseViolation):
        dispatch(
            "unwrap_uvs", {"object_id": "box1"},
            role=ToolRole.POLISH, orchestrator=orchestrator, lease=write_lease,
        )


def test_the_role_the_caller_declares_cannot_narrow_what_it_may_call(
    orchestrator, write_lease, fake_scene,
) -> None:
    """The other direction of the same rule. An agent that mislabels its own call must
    not be refused a tool its lease genuinely holds — otherwise the lease is not the
    authority, the request string still is, and two sources of truth remain."""
    result = dispatch(
        "add_primitive", _PRIMITIVE,
        role=ToolRole.EXPORT, orchestrator=orchestrator, lease=write_lease,
    )
    assert result["ok"] is True
    assert fake_scene.document.head == 1


def test_a_lease_narrowed_to_one_role_cannot_reach_another_roles_tool(
    orchestrator, write_lease, fake_scene,
) -> None:
    """A multi-agent run partitions roles per agent. If a narrowed lease still permits
    everything legal in the phase, partitioning buys nothing and one agent's mistake
    reaches every tool in the phase."""
    _narrow(fake_scene, write_lease, (ToolRole.INSPECT,))
    narrowed = fake_scene.document.active_lease

    with pytest.raises(PhaseViolation):
        dispatch(
            "add_primitive", _PRIMITIVE,
            role=ToolRole.BLOCKOUT, orchestrator=orchestrator, lease=narrowed,
        )


# --------------------------------------------------------------- the refusal is usable

def test_a_refusal_names_the_phase_the_tool_and_how_to_promote(
    orchestrator, write_lease,
) -> None:
    """Gate A 4.2, in the user's own words: an agent is told which rule broke and what to
    do next. ADR-012 removed the promotion override, so an agent that cannot work out how
    to move forward from a refusal has no escape at all and will retry the same call
    forever."""
    with pytest.raises(PhaseViolation) as excinfo:
        dispatch(
            "unwrap_uvs", {"object_id": "box1"},
            role=ToolRole.POLISH, orchestrator=orchestrator, lease=write_lease,
        )
    message = str(excinfo.value)
    assert "unwrap_uvs" in message
    assert "blockout" in message
    assert "polish" in message
    assert "promote_phase" in message


def test_an_unknown_tool_name_lists_what_is_callable_now_not_the_whole_catalogue(
    orchestrator,
) -> None:
    """An agent that misnames a tool needs the shortlist it should have chosen from. The
    whole catalogue is neither short nor relevant — only the tools legal in this phase
    are, and a refusal that dumps everything is one an agent cannot act on."""
    from contracts import PHASE_ROLES
    from mcp_server import tools_for

    with pytest.raises(Exception) as excinfo:
        dispatch("not_a_real_tool", {}, role=ToolRole.BLOCKOUT, orchestrator=orchestrator)

    message = str(excinfo.value)
    assert "not_a_real_tool" in message
    assert "add_primitive" in message  # legal in blockout
    legal_now = {spec.name for role in PHASE_ROLES[Phase.BLOCKOUT] for spec in tools_for(role)}
    illegal_now = {
        spec.name
        for role in (ToolRole.POLISH, ToolRole.DETAIL, ToolRole.EXPORT)
        for spec in tools_for(role)
        if role not in PHASE_ROLES[Phase.BLOCKOUT] and spec.name not in legal_now
    }
    assert not (illegal_now & set(message.split())), "listed tools this phase cannot call"


# ------------------------------------------------------ readers do not need the lock

def test_a_read_only_tool_runs_with_no_write_lease_at_all(orchestrator) -> None:
    """ADR-007's whole point: many INSPECT agents run beside the one writer. Requiring a
    write lease to read would serialise every reader behind the writer and delete the
    parallelism the multi-agent design is built on."""
    result = dispatch("get_phase", {}, role=ToolRole.INSPECT, orchestrator=orchestrator, lease=None)
    assert result["phase"] == "blockout"


def test_a_read_only_tool_runs_while_another_agent_holds_the_write_lock(
    orchestrator,
) -> None:
    """The same guarantee under contention, which is the case that actually matters: a
    reader blocked by a live writer is a reader that cannot review work in progress."""
    orchestrator.acquire(holder="the-writer", phase=Phase.BLOCKOUT)
    result = dispatch("list_objects", {}, role=ToolRole.INSPECT, orchestrator=orchestrator)
    assert "objects" in result


# ------------------------------------------------------- it is not a security boundary

def test_the_authorisation_module_says_it_is_not_a_security_boundary() -> None:
    """ADR-009 gives every connected agent arbitrary code execution and full disk access by
    explicit user choice. A docstring implying this check contains any of that would lead
    the next reader — human or agent — to trust it as a sandbox and to build on a defence
    that does not exist, which is how a wrong security claim ends up in SECURITY.md."""
    import importlib

    module = importlib.import_module("mcp_server.authorize")
    text = (module.__doc__ or "").lower()
    assert "not a security boundary" in text
    assert "adr-009" in text


def test_authorisation_adds_no_sandbox_to_raw_execution(orchestrator, fake_scene) -> None:
    """Silently narrowing a capability the user chose is as much a defect as failing to
    build it. ADMIN is legal in every phase, and raw execution must stay unrestricted —
    no allowlist, no AST check, no phase that quietly disables it."""
    lease = orchestrator.acquire(holder="admin", phase=Phase.BLOCKOUT)
    result = dispatch(
        "raw_execute", {"source": "x = 1"},
        role=ToolRole.ADMIN, orchestrator=orchestrator, lease=lease,
    )
    assert result["ok"] is True
    assert fake_scene.document.operations[-1].opaque is True
