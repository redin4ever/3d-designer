"""Conformance checks for ``RawOps.execute`` — arbitrary Python against the live context.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/raw.py``.
"""

from __future__ import annotations

import pytest

from contracts import EngineProtocol, Vec3

__all__ = [
    "check_execute_runs_against_live_context",
    "check_execute_propagates_a_raising_source",
]


def check_execute_runs_against_live_context(engine: EngineProtocol) -> None:
    """If ``execute`` runs against a private copy of the scene rather than the live engine,
    it becomes theatre — it looks like it ran, but nothing a later call observes changed,
    and ADR-009's "record every invocation" guarantee is worthless."""
    ns = engine.execute(
        "engine.create_primitive('via_exec', 'cube', Vec3(1, 1, 1))",
        namespace={"engine": engine, "Vec3": Vec3},
    )
    assert engine.exists("via_exec"), "execute() did not mutate the live engine"
    assert ns["engine"] is engine


def check_execute_propagates_a_raising_source(engine: EngineProtocol) -> None:
    """``RawOps.execute``'s docstring is explicit: this method must not catch and rewrap the
    supplied source's exception — the *caller* wraps it into ``EngineError``. An engine that
    wraps here breaks every call site's wrapper, which expects the original exception as
    ``__cause__``, and an agent loops on a traceback it cannot act on."""
    with pytest.raises(ZeroDivisionError):
        engine.execute("1 / 0")
