"""How much of an action report to actually send (Gate B 4.3).

One ``add_railing`` returned ~3,398 tokens listing dimensions and a triangle count for all 40
objects it made; a small room cost ~5,400 tokens of check output per pass. Above
:data:`contracts.DETAIL_THRESHOLD` objects the per-object list is replaced by a breakdown and
totals, and the report says so.

Two rules this module exists to keep:

- **No defect is ever dropped.** Findings are the reason the channel costs anything; the
  inventory is not. Only per-object *detail* is traded away, which is why defects are not
  even passed through here.
- **Nothing is omitted silently.** A summarised report that does not say it summarised reads
  as a complete one — the same failure ``checks_skipped`` exists to prevent, one field over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from contracts import DETAIL_THRESHOLD, EngineProtocol, Measurement

__all__ = ["Detail", "summarise", "DETAIL_HINT"]

DETAIL_HINT = "call describe_object(<id>) for per-object dimensions and triangle count"
"""Named concretely, because "ask for more detail" is not something an agent can act on.
``describe_object`` is being added by the tool-surface pass alongside this one."""

_TRAILING_INDEX = re.compile(r"[-_. ]?\d+$")


@dataclass(frozen=True, slots=True)
class Detail:
    """The size-dependent half of an :class:`contracts.ActionReport`."""

    measurements: tuple[Measurement, ...] = ()
    breakdown: tuple[tuple[str, int], ...] = ()
    detail_omitted: int = 0
    detail_hint: str = ""
    total_triangles: int = 0


def _stem(object_id: str) -> str:
    """``post_07`` → ``post``. What forty objects from one operation have in common.

    A breakdown of ``40x add_railing`` tells an agent nothing it did not already know — it
    called ``add_railing``. ``20x post, 19x baluster, 1x rail`` is what the omitted list
    would have shown it.
    """
    return _TRAILING_INDEX.sub("", object_id) or object_id


def summarise(
    engine: EngineProtocol, changed: tuple[str, ...], *, threshold: int = DETAIL_THRESHOLD
) -> Detail:
    """Measure what changed, and decide how much of it to send.

    Never raises: a measurement failure must not fail an operation that already succeeded.
    The report says less; the agent still gets its result.
    """
    import measure

    measurements: list[Measurement] = []
    total = 0
    for object_id in changed:
        try:
            dimensions = measure.dimensions(engine, object_id)
            triangles = measure.triangle_count(engine, object_id)
        except Exception:  # noqa: BLE001 — a stale id must not sink the report
            continue
        measurements.extend((dimensions, triangles))
        if isinstance(triangles.value, (int, float)):
            total += int(triangles.value)

    if len(changed) <= threshold:
        return Detail(measurements=tuple(measurements), total_triangles=total)

    counts: dict[str, int] = {}
    for object_id in changed:
        stem = _stem(object_id)
        counts[stem] = counts.get(stem, 0) + 1
    return Detail(
        breakdown=tuple(sorted(counts.items())),
        detail_omitted=len(changed),
        detail_hint=DETAIL_HINT,
        total_triangles=total,
    )
