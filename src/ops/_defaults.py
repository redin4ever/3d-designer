"""The dimensional defaults this library carries, and the lines that report them.

Gate A 6.4, in the user's own framing, chose that this tool never carries a table of
real-world dimensions: the agent supplies every one. The Phase 6 drift review found
``add_railing`` quietly defaulting three cross-sections — 50mm posts, 30mm balusters, a
50mm top rail — invisibly, which is that table under another name. Gate B 1.4 kept the
defaults and required them **reported**, through
:attr:`~contracts.OperationResult.assumptions`.

So this file is the table, made singular and made visible: one place that knows what gets
supplied, and every value in it comes back to the agent the moment it is used. An agent
that can see what was assumed on its behalf can correct it.

**What belongs here.** A default a modeller would read as a decision about *size* — a
cross-section, a thickness, a clearance. A number that came from knowing something about
the real world.

**What does not.** A count, a ratio, a flag (``keep_upright``), or a neutral identity:
``origin`` defaulting to the world origin, ``transform`` to identity, ``sill_height`` to 0.
None of those is a dimension taken from the real world — each is what "I did not say"
already means — and reporting them would put a line on nearly every call, which is how the
one line that matters gets skimmed past. The sweep in ``assumptions_test.py`` holds this
boundary from the other side: no operation may report a parameter its caller supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["DIMENSION_DEFAULTS", "DimensionDefault", "resolve_dimensions"]


@dataclass(frozen=True, slots=True)
class DimensionDefault:
    """One supplied dimension: what it is, and how to say so in one line."""

    value: Any
    described: str
    """The value as a modeller reads it, units included — ``"0.05 x 0.05 m"``."""

    what: str
    """What it dimensions, so the line means something without the schema to hand."""


DIMENSION_DEFAULTS: dict[str, dict[str, DimensionDefault]] = {
    "add_railing": {
        "post_size": DimensionDefault((0.05, 0.05), "0.05 x 0.05 m", "the post cross-section"),
        "baluster_size": DimensionDefault(
            (0.03, 0.03), "0.03 x 0.03 m", "the baluster cross-section"
        ),
        "rail_size": DimensionDefault(
            (0.05, 0.05), "0.05 x 0.05 m", "the top rail's cross-section"
        ),
    },
}


def resolve_dimensions(
    kind: str, params: dict[str, Any]
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """The dimensions ``kind`` will build with, and one report line per default it used.

    Returns ``(values, assumptions)``. ``values`` always carries every dimension in
    ``kind``'s table, whether it was supplied or defaulted, so a handler reads them from one
    place instead of repeating the literal at the call site — which is how the three railing
    literals drifted out of sight in the first place. ``assumptions`` names only what the
    caller left out: a report that also lists what the agent itself passed is noise.
    """
    table = DIMENSION_DEFAULTS.get(kind, {})
    values: dict[str, Any] = {}
    assumed: list[str] = []
    for name, default in table.items():
        if name in params:
            values[name] = params[name]
            continue
        values[name] = default.value
        assumed.append(
            f"{name} not given — used {default.described} for {default.what}; "
            f"pass {name} to choose it yourself"
        )
    return values, tuple(assumed)
