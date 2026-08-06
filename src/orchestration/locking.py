"""The single write lock — implements ``contracts.WriteLockManager`` (ADR-007).

Phase gating *is* the concurrency-control mechanism, not a separate thing that
cooperates with one: exactly one lease may be live at a time, over the whole run, and
every mutation must present it. Read-only INSPECT-role callers never need one — that is
the entire mechanism that makes "many readers, one writer" real rather than a suggestion
(see ``proposals.py``, whose ``propose`` takes no lease parameter at all).

Nothing here computes anything yet — every method raises until an implementer replaces
the body (Rule 4 — tests come first). The lease itself is expected to live in exactly one
place: ``self._scene.document.active_lease`` (``contracts.SceneDocument``), which
already carries a ``require_lease()`` check with the right error shape — this mixin's
``verify`` should delegate to it rather than re-deriving the comparison, so there is
exactly one place "is this lease live" is decided.
"""

from __future__ import annotations

import uuid

from contracts import LockContention, Phase, WriteLease

_NOT_IMPLEMENTED = "orchestration.{name}: not implemented"


class LockingMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def acquire(self, holder: str, phase: Phase, *, ttl_ops: int = 64) -> WriteLease:
        """Grant the write lock to ``holder``, or raise :class:`contracts.LockContention`.

        Once implemented:

        - If no lease is live, or the live one is stale (``WriteLease.is_stale`` against
          ``self._scene.document.head`` — the operation count is the run's only clock,
          deliberately not wall-clock time, so a paused run does not burn a holder's
          lease and tests stay deterministic), grant a new one: ``granted_at_op`` is the
          current head, ``expires_at_op`` is ``granted_at_op + ttl_ops``.
        - If a live, non-stale lease is held by someone else, raise
          :class:`contracts.LockContention` naming that holder and its expiry — never a
          bare ``RuntimeError``. An agent told who holds the lock and when it expires
          can wait usefully; one given a traceback retries immediately, forever.
        - Re-acquiring by the *same* holder while their own lease is still live is left
          open (renew vs. contend with self) — no test in ``locking_test.py`` pins it
          down.
        - The granted lease is written to ``self._scene.document.active_lease`` — it
          must be held in exactly that one place. A lease value an agent builds itself
          proves nothing (``contracts.WriteLease``'s own docstring).
        """
        doc = self._scene.document

        # The clock has to advance even when nothing is being applied. Expiry used to be
        # measured against `doc.head`, which only moves when an operation is applied —
        # which only the current lease holder can do. So a holder that died mid-operation
        # froze the clock at the exact moment it stopped, its lease could never go stale,
        # and no other agent could ever acquire. The run wedged permanently, which is the
        # one outcome a fully autonomous design cannot recover from. Agents die (Rule 6);
        # counting attempts means a waiting agent advances the clock by waiting.
        self._lock_tick = getattr(self, "_lock_tick", 0) + 1
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
        )
        doc.active_lease = lease
        return lease

    def release(self, lease: WriteLease) -> None:
        """Give up the lock.

        A release of a lease that is not the live one is left to the implementer as a
        no-op or a raise — either is safe, because the caller cannot clear a lock they
        never actually held either way. Clearing the *correct* live lease out from under
        its actual holder would not be, and must never happen from a mismatched
        ``lease``.
        """
        doc = self._scene.document
        if doc.active_lease is not None and doc.active_lease.lease_id == lease.lease_id:
            doc.active_lease = None

    def current(self) -> WriteLease | None:
        """The live lease, or ``None``. Once implemented, read straight from
        ``self._scene.document.active_lease`` — one field, one truth, never a second
        copy this class keeps of its own."""
        return self._scene.document.active_lease

    def verify(self, lease: WriteLease) -> None:
        """Raise :class:`contracts.LockContention` unless ``lease`` is the live one.

        Called before every mutation (``reporting.perform``, ``proposals.accept``) — this
        is the one check that makes the write lock real rather than advisory. Expected to
        delegate to ``self._scene.document.require_lease(lease)``, which already
        implements exactly this comparison and this error shape.
        """
        self._scene.document.require_lease(lease)
