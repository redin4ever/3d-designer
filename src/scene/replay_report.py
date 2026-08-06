"""What a rebuild actually managed to do — the shape ``replay`` hands back.

``replay`` used to return ``None`` and abort on the first operation it could not re-run,
which made a single unreplayable entry fatal for the rest of the session (F-010). It now
skips and carries on, and this is how that reaches the caller: a replay that quietly
dropped operations is worse than one that failed, because the operator is left looking at
a scene that appears whole and is missing work nobody mentioned.

Data shapes only — no behaviour. ``document.py`` builds these; ``history.py`` forwards
them to listeners.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SkippedOperation", "ReplayReport"]


@dataclass(frozen=True, slots=True)
class SkippedOperation:
    """One operation the rebuild could not re-run, and why.

    ``reason`` is the engine's or handler's own message rather than a generic label: an
    agent told *"no object named 'bad_hole'"* can act, and one told *"an operation was
    skipped"* cannot.
    """

    op_id: str
    kind: str
    reason: str

    def describe(self) -> str:
        return f"{self.op_id} ({self.kind}): {self.reason}"


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """The outcome of one rebuild of the scene from the log."""

    applied: int = 0
    skipped: tuple[SkippedOperation, ...] = ()
    restored_from: str = ""
    """The geometry snapshot this rebuild started from, when it started from one rather
    than from ``engine.reset()``. Names the barrier restore that avoided re-running an
    opaque operation, so "we restored" and "we replayed" are distinguishable after the
    fact rather than both reported as ``FULL_RESYNC``."""

    @property
    def complete(self) -> bool:
        """True when every active operation ran. Deliberately not ``bool(skipped)``
        inverted at each call site — three call sites is three chances to get it
        backwards."""
        return not self.skipped

    def describe(self) -> str:
        """One line, safe for a Windows console (cp1252) — this text travels into agent
        tool responses and log files, and a non-ASCII character there raises
        ``UnicodeEncodeError`` and takes the whole call down."""
        parts = [f"replayed {self.applied} operation(s)"]
        if self.restored_from:
            parts.append(f"from snapshot {self.restored_from}")
        if self.skipped:
            parts.append(
                f"SKIPPED {len(self.skipped)}: "
                + "; ".join(s.describe() for s in self.skipped)
            )
        return " | ".join(parts)
