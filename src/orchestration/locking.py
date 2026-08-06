"""The single write lock — implements ``contracts.WriteLockManager`` (ADR-007, ADR-013).

Phase gating *is* the concurrency-control mechanism, not a separate thing that cooperates
with one: exactly one lease may be live at a time, over the whole run, and every mutation
must present it. Read-only INSPECT-role callers never need one — that is the entire
mechanism that makes "many readers, one writer" real rather than a suggestion (see
``proposals.py``, whose ``propose`` takes no lease parameter at all).

Two things this file is responsible for that a reader should not have to infer:

**The lease is where role authority lives (ADR-013).** ``acquire`` takes the roles it
grants and puts them on the lease; ``authorization.py`` reads them back. Before Gate B the
role travelled with each *call*, supplied by the caller, so an agent held any role it cared
to name.

**Every state transition here is guarded by a real mutex.** ``acquire`` is a check
("is a live lease held?") followed by a write ("take it"), and until this pass those two
steps ran unsynchronised: eight threads racing produced *three* simultaneous winners in the
first round of ``concurrency_test.py``, each believing it held the only write lock. A
single-writer guarantee that only holds when nobody is racing for it guarantees nothing —
racing for it is the case it exists for.
"""

from __future__ import annotations

import uuid

from contracts import LockContention, Phase, ToolRole, WriteLease


class LockingMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def acquire(
        self,
        holder: str,
        phase: Phase,
        *,
        ttl_ops: int = 64,
        roles: tuple[ToolRole, ...] = (),
    ) -> WriteLease:
        """Grant the write lock to ``holder``, or raise :class:`contracts.LockContention`.

        ``roles`` narrows what the returned lease permits. Empty — the default, and the
        ordinary case for a single-agent session — grants everything legal in ``phase``
        (``WriteLease.granted_roles``). A multi-agent run narrows it per agent, and a caller
        cannot widen it afterwards because :class:`contracts.WriteLease` is frozen and only
        this method issues one.

        Re-acquiring by the **same holder** renews rather than contends, and re-states the
        roles — an agent that has finished building and wants to inspect, or one that
        discovers mid-phase that it also needs to align something, must be able to narrow or
        widen without releasing. Releasing is the one moment another agent can take the lock
        away and leave the run half-built, so making that the price of changing roles would
        push agents towards holding more authority than they need.

        A live lease held by *anyone else* raises :class:`contracts.LockContention` naming
        that holder and its expiry — never a bare ``RuntimeError``. An agent told who holds
        the lock and when it expires can wait usefully; one given a traceback retries
        immediately, forever.
        """
        with self._write_mutex:
            doc = self._scene.document

            # The clock has to advance even when nothing is being applied. Expiry used to be
            # measured against `doc.head`, which only moves when an operation is applied —
            # which only the current lease holder can do. So a holder that died mid-operation
            # froze the clock at the exact moment it stopped, its lease could never go stale,
            # and no other agent could ever acquire. The run wedged permanently, which is the
            # one outcome a fully autonomous design cannot recover from. Agents die (Rule 6);
            # counting attempts means a waiting agent advances the clock by waiting.
            self._lock_tick += 1
            now = doc.head + self._lock_tick

            current = doc.active_lease
            if current is not None and not current.is_stale(now) and current.holder != holder:
                raise LockContention(holder=current.holder, expires_at_op=current.expires_at_op)

            lease = WriteLease(
                holder=holder,
                phase=phase,
                lease_id=uuid.uuid4().hex,
                granted_at_op=doc.head,
                expires_at_op=now + ttl_ops,
                roles=tuple(roles),
            )
            doc.active_lease = lease
            return lease

    def release(self, lease: WriteLease) -> None:
        """Give up the lock.

        Releasing a lease that is not the live one is a no-op: the caller did not hold the
        lock, so there is nothing of theirs to give up. Clearing the *correct* live lease out
        from under its actual holder on a mismatched argument would be a genuine hazard, and
        the identity check is what rules it out.
        """
        with self._write_mutex:
            doc = self._scene.document
            if doc.active_lease is not None and doc.active_lease.lease_id == lease.lease_id:
                doc.active_lease = None

    def current(self) -> WriteLease | None:
        """The live lease, or ``None`` — read straight from
        ``self._scene.document.active_lease``. One field, one truth, never a second copy this
        class keeps of its own."""
        return self._scene.document.active_lease

    def verify(self, lease: WriteLease) -> None:
        """Raise :class:`contracts.LockContention` unless ``lease`` is the live one.

        Called before every mutation (``reporting.perform``, ``proposals.accept``) — this is
        the one check that makes the write lock real rather than advisory. Delegates to
        ``SceneDocument.require_lease``, which already implements exactly this comparison and
        this error shape, so "is this lease live" is decided in exactly one place.
        """
        self._scene.document.require_lease(lease)
