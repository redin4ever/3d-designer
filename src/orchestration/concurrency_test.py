"""Real concurrency against the real ``Scene`` — the multi-agent guarantee, actually raced.

ADR-007's single-writer rule is the load-bearing safety property of the whole design, and
until this file every lock test in the codebase called ``acquire``/``perform`` sequentially
on one thread. A lock that is only ever exercised by one thread at a time is not a tested
lock; it is a tested sequence of function calls that happens to contain a lock.

These tests drive the genuine ``scene.Scene`` over a genuine ``testing.FakeEngine`` from
genuine ``threading.Thread``s, released together by a ``threading.Barrier`` so contention is
the point rather than an accident. There are no sleeps: every wait is a barrier or a join,
because a sleep long enough to be reliable is a test that takes seconds and a sleep short
enough to be fast is a test that is flaky (``.claude/rules/testing.md``).

``sys.setswitchinterval`` is lowered for the duration of the racing tests. That does not
make a passing run prove absence of a race — nothing can — but it widens the window an
unguarded read-modify-write is caught in from "essentially never" to "reliably", which is
the difference between a regression test and a decoration.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field

import pytest

from contracts import (
    LockContention,
    Operation,
    OperationResult,
    Phase,
    PhaseViolation,
    ToolRole,
    Vec3,
)
from orchestration import Orchestrator
from scene import Scene
from testing import FakeEngine

WRITERS = 8
"""Enough racing threads that a lost update is likely rather than theoretical, and few
enough that the whole file still runs in well under a second."""


def _add_box(engine, op: Operation) -> OperationResult:
    """A real handler: it creates real geometry through the real engine.

    Deliberately not a no-op. ``Scene.apply`` only records an operation whose handler
    succeeded, so a handler that does nothing would let the log stay consistent for reasons
    that have nothing to do with the lock.
    """
    object_id = op.params["object_id"]
    engine.create_primitive(object_id, "cube", Vec3(0.5, 0.5, 0.5))
    return OperationResult(op_id=op.op_id, ok=True, produced_objects=(object_id,))


@pytest.fixture
def live():
    """A real ``Scene`` over a real ``FakeEngine``, wired to a real ``Orchestrator``.

    Not this package's ``FakeScene``: the point of this file is the interaction between
    orchestration's lock and ``scene``'s own document mutation, and a double cannot exhibit
    an interaction it does not implement.
    """
    engine = FakeEngine()
    scene = Scene(engine, {"add_box": _add_box}, scene_id="concurrency")
    return scene, Orchestrator(scene)


@pytest.fixture(autouse=True)
def _aggressive_preemption():
    """Force the interpreter to switch threads far more often than the 5 ms default.

    Without this, the window between ``operations.append(op)`` and ``head = len(...)`` is a
    handful of bytecodes wide and a genuine lost update shows up perhaps once in ten
    thousand runs — which is a race that ships.
    """
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(previous)


@dataclass
class Outcome:
    """What every worker thread reports back.

    A dataclass rather than a bag of lists because a thread that dies must be
    distinguishable from a thread that succeeded quietly (Rule 6: silence and success are
    the same shape), and that means recording the exception rather than its absence.
    """

    won: list[str] = field(default_factory=list)
    contended: list[LockContention] = field(default_factory=list)
    violations: list[PhaseViolation] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    unexpected: list[BaseException] = field(default_factory=list)
    guard: threading.Lock = field(default_factory=threading.Lock)

    def record(self, bucket: str, value) -> None:
        with self.guard:
            getattr(self, bucket).append(value)


def _run(targets) -> None:
    """Start every callable at once and join them all. No sleeps, no polling."""
    threads = [threading.Thread(target=t, name=f"t{i}") for i, t in enumerate(targets)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a worker thread never finished"


# --------------------------------------------------------------- the lock, under contention


def test_exactly_one_of_many_racing_threads_wins_the_write_lock(live) -> None:
    """If two threads can both come out of ``acquire`` holding a lease, ADR-007's guarantee
    is gone and two agents mutate one scene believing each is the only writer — the exact
    failure the entire phase/lock design exists to rule out. Sequential tests cannot see
    this: the check-then-write in ``acquire`` is only wrong when two threads are inside it
    at the same moment."""
    _scene, orch = live
    rounds = 40

    for round_index in range(rounds):
        gate = threading.Barrier(WRITERS)
        outcome = Outcome()

        def attempt(n: int) -> None:
            gate.wait()
            try:
                lease = orch.acquire(f"writer-{n}", Phase.BLOCKOUT, ttl_ops=1_000_000)
                outcome.record("won", lease.holder)
            except LockContention as exc:
                outcome.record("contended", exc)
            except BaseException as exc:  # noqa: BLE001 — a dead thread must not read as clean
                outcome.record("unexpected", exc)

        _run([lambda n=n: attempt(n) for n in range(WRITERS)])

        assert outcome.unexpected == []
        assert len(outcome.won) == 1, (
            f"round {round_index}: {len(outcome.won)} threads believe they hold the only "
            f"write lock ({outcome.won})"
        )
        assert len(outcome.contended) == WRITERS - 1
        winner = outcome.won[0]
        for exc in outcome.contended:
            assert exc.holder == winner, "a refusal named a holder that never held the lock"
            assert exc.expires_at_op > 0, "a refusal with no expiry gives a waiter nothing"
        orch.release(orch.current())


def test_a_refusal_names_the_holder_and_the_expiry_so_a_waiter_can_wait(live) -> None:
    """An agent told only "no" retries immediately, forever, and burns the run's whole budget
    on a lock it will never get by spinning. Told who holds it and until when, it can do
    something else — which is what makes ``LockContention`` a named error rather than a bare
    ``RuntimeError``."""
    _scene, orch = live
    held = orch.acquire("writer-a", Phase.BLOCKOUT, ttl_ops=1_000_000)
    outcome = Outcome()
    gate = threading.Barrier(WRITERS)

    def attempt(n: int) -> None:
        gate.wait()
        try:
            orch.acquire(f"writer-{n}", Phase.BLOCKOUT)
        except LockContention as exc:
            outcome.record("contended", exc)
        except BaseException as exc:  # noqa: BLE001
            outcome.record("unexpected", exc)

    _run([lambda n=n: attempt(n) for n in range(WRITERS)])

    assert outcome.unexpected == []
    assert len(outcome.contended) == WRITERS
    assert {exc.holder for exc in outcome.contended} == {"writer-a"}
    assert {exc.expires_at_op for exc in outcome.contended} == {held.expires_at_op}
    assert all("wait for operation" in str(exc) for exc in outcome.contended)


def test_the_loser_acquires_once_the_winner_releases(live) -> None:
    """A lock that is never handed back is a lock that ends the run at its first contention.
    The loser retrying after a genuine release must succeed, or every multi-agent phase
    degrades to whichever agent happened to call ``acquire`` first."""
    _scene, orch = live
    ready = threading.Barrier(2)
    released = threading.Event()
    outcome = Outcome()

    def winner() -> None:
        lease = orch.acquire("writer-a", Phase.BLOCKOUT, ttl_ops=1_000_000)
        ready.wait()
        outcome.record("won", lease.holder)
        orch.release(lease)
        released.set()

    def loser() -> None:
        ready.wait()
        try:
            orch.acquire("writer-b", Phase.BLOCKOUT)
        except LockContention as exc:
            outcome.record("contended", exc)
        # Wait on the winner's release event, not on a sleep: the retry must be caused by
        # the release, not by a duration that happens to be long enough today.
        assert released.wait(timeout=30)
        lease = orch.acquire("writer-b", Phase.BLOCKOUT)
        outcome.record("won", lease.holder)

    _run([winner, loser])

    assert outcome.unexpected == []
    assert "writer-b" in outcome.won
    assert orch.current().holder == "writer-b"


def test_a_dead_writers_expired_lease_is_reclaimed_by_a_waiter(live) -> None:
    """Agents die mid-operation (Rule 6) and a dead holder never releases. Without expiry the
    run wedges permanently with nobody watching — the one outcome a fully autonomous design
    cannot recover from. This regressed once already, when expiry was measured against a
    clock only the lock holder could advance."""
    _scene, orch = live
    orch.acquire("dead-writer", Phase.BLOCKOUT, ttl_ops=2)  # never released: the agent died
    outcome = Outcome()
    gate = threading.Barrier(2)

    def waiter(n: int) -> None:
        gate.wait()
        for _ in range(64):  # bounded: a stall must fail the test, not hang it
            try:
                lease = orch.acquire(f"waiter-{n}", Phase.BLOCKOUT, ttl_ops=2)
                outcome.record("won", lease.holder)
                return
            except LockContention as exc:
                outcome.record("contended", exc)

    _run([lambda n=n: waiter(n) for n in range(2)])

    assert outcome.unexpected == []
    # At least one waiter must get through. Both getting through is not required and is not
    # the property under test: once the first has taken over, the second is contending with a
    # *live* holder, which is the lock working exactly as intended.
    assert len(outcome.won) >= 1, "the dead writer wedged the run — nobody could ever acquire"
    assert all(holder.startswith("waiter-") for holder in outcome.won)
    assert "dead-writer" in {exc.holder for exc in outcome.contended}, (
        "nobody was ever told who was holding the lock they could not get"
    )
    # The second waiter legitimately contends against the first once it has taken over —
    # that is the lock working, not the dead holder still wedging anything.
    assert {exc.holder for exc in outcome.contended} <= {"dead-writer", "waiter-0", "waiter-1"}


# ------------------------------------------------------------------ the log, under contention


def test_two_writers_interleaving_perform_leave_an_internally_consistent_log(live) -> None:
    """The log is the source of truth — geometry is generated from it — so a torn log is not
    a bookkeeping problem, it is a scene that silently no longer matches what was built.
    ``SceneDocument.append`` truncates anything past ``head``; two threads inside it at once
    can have one truncate the other's just-appended operation away while its ``perform``
    still reports success. That is a lost operation nobody is told about."""
    scene, orch = live
    per_writer = 25
    lease = orch.acquire("writer", Phase.BLOCKOUT, ttl_ops=1_000_000)
    gate = threading.Barrier(2)
    outcome = Outcome()

    def writer(tag: str) -> None:
        gate.wait()
        for i in range(per_writer):
            op = Operation(
                op_id=f"{tag}-{i}",
                kind="add_box",
                params={"object_id": f"{tag}_{i}"},
                produced_objects=(f"{tag}_{i}",),
            )
            try:
                report = orch.perform(op, lease)
                if report.ok:
                    outcome.record("applied", op.op_id)
            except BaseException as exc:  # noqa: BLE001
                outcome.record("unexpected", exc)

    _run([lambda: writer("a"), lambda: writer("b")])

    assert outcome.unexpected == []
    doc = scene.document
    logged = [op.op_id for op in doc.operations]
    assert len(logged) == len(set(logged)), "the log contains a duplicate op_id"
    assert doc.head == len(doc.operations), (
        f"head {doc.head} does not match {len(doc.operations)} logged operations — the "
        "undo pointer and the log disagree about what happened"
    )
    assert set(outcome.applied) == set(logged), (
        "an operation reported as applied is missing from the log, or the log holds one "
        "nobody was told about"
    )
    assert len(logged) == 2 * per_writer


def test_a_phase_violation_on_one_thread_does_not_disturb_another_threads_operation(
    live,
) -> None:
    """Refusals happen constantly in a multi-agent run — that is what the role partition is
    for. If raising one could interleave badly with a concurrent write, then enforcing
    ADR-013 would itself corrupt the scene, and the safe move would be to stop enforcing it.
    Both guarantees have to hold at once or neither is usable."""
    scene, orch = live
    lease = orch.acquire("writer", Phase.BLOCKOUT, ttl_ops=1_000_000)
    attempts = 40
    gate = threading.Barrier(2)
    outcome = Outcome()

    def refused() -> None:
        gate.wait()
        for _ in range(attempts):
            try:
                orch.authorize("unwrap_uvs", (ToolRole.POLISH,), lease)
                outcome.record("unexpected", AssertionError("a polish tool passed in blockout"))
            except PhaseViolation as exc:
                outcome.record("violations", exc)

    def writer() -> None:
        gate.wait()
        for i in range(attempts):
            op = Operation(
                op_id=f"w-{i}",
                kind="add_box",
                params={"object_id": f"w_{i}"},
                produced_objects=(f"w_{i}",),
            )
            try:
                orch.perform(op, lease)
                outcome.record("applied", op.op_id)
            except BaseException as exc:  # noqa: BLE001
                outcome.record("unexpected", exc)

    _run([refused, writer])

    assert outcome.unexpected == []
    assert len(outcome.violations) == attempts
    doc = scene.document
    assert [op.op_id for op in doc.operations] == [f"w-{i}" for i in range(attempts)]
    assert doc.head == len(doc.operations)
    assert scene.engine.list_objects() == sorted(f"w_{i}" for i in range(attempts))


# ------------------------------------------------------------- many readers, one writer


def test_many_inspect_readers_run_beside_a_live_writer_and_none_is_refused(live) -> None:
    """"Many read, one writes" is the whole reason parallelism is real here (ADR-007). If a
    reader could be refused — or blocked out — because somebody holds the write lock, every
    inspect agent would serialise behind the writer and the multi-agent design would be a
    single-agent design paying for coordination it does not get."""
    scene, orch = live
    lease = orch.acquire("writer", Phase.BLOCKOUT, ttl_ops=1_000_000)
    readers = 12
    reads_each = 20
    gate = threading.Barrier(readers + 1)
    outcome = Outcome()
    seen: list[int] = []
    seen_guard = threading.Lock()

    def reader(n: int) -> None:
        gate.wait()
        for i in range(reads_each):
            try:
                orch.pending()
                orch.find_conflicts()
                _ = orch.phase
                orch.propose(_proposal(f"reader-{n}", f"p-{n}-{i}"))
                orch.authorize("inspect_defects", (ToolRole.INSPECT,), None)
                with seen_guard:
                    seen.append(len(scene.document.operations))
            except BaseException as exc:  # noqa: BLE001
                outcome.record("unexpected", exc)

    def writer() -> None:
        gate.wait()
        for i in range(30):
            op = Operation(
                op_id=f"w-{i}",
                kind="add_box",
                params={"object_id": f"w_{i}"},
                produced_objects=(f"w_{i}",),
            )
            try:
                orch.perform(op, lease)
            except BaseException as exc:  # noqa: BLE001
                outcome.record("unexpected", exc)

    _run([lambda n=n: reader(n) for n in range(readers)] + [writer])

    assert outcome.unexpected == [], f"a reader was refused while a writer held the lock: {outcome.unexpected}"
    assert len(orch.pending()) == readers * reads_each
    assert scene.document.head == len(scene.document.operations) == 30
    assert max(seen) > 0, "no reader ever observed the writer's work — they did not overlap"


def _proposal(author: str, proposal_id: str):
    from contracts import Proposal

    return Proposal(
        proposal_id=proposal_id,
        author=author,
        target_objects=(f"{proposal_id}-object",),
        operation_kind="add_box",
    )
