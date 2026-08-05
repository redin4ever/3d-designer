"""Keeps every role's visible tool set within the accuracy-optimal bound (ADR-003).

Registry content is declared independently by several sibling modules, each of which
reasonably assigns its own tools to whichever :class:`contracts.ToolRole` matches its own
domain (``Phase``'s own docstring: REFINE is "correct topology, close gaps, resolve
clipping, fix alignment") — ``ops``, ``gaps`` and ``align`` each independently and
correctly land some or all of their tools on ``ToolRole.REFINE``, and nothing anywhere
enforces the *combined* total across modules built in parallel by separate agents
(Rule 5). As of this writing that puts ``REFINE`` at ``ops`` (4) + ``gaps`` (8) + ``align``
(7) = 19 tools — more than double the 8-tool cap ``contracts.ToolRole``'s own docstring
describes as load-bearing.

This is a genuine cross-module coordination gap, not a defect in any one contributor —
``src/gaps/`` and ``src/align/`` are each independently ``GREEN``, correctly tested, and
outside this module's write boundary to change (Rule 5). Until the contributing modules
consolidate their declarations (``gaps.GAPS_SPECS``'s own ``repair`` tool already shows one
workable pattern — one umbrella tool instead of several granular ones) or
``contracts.ToolRole`` gains finer granularity, ``mcp`` — which owns registry *policy*, not
content (``.pipeline/modules.json``'s own note on this module) — enforces the bound here,
fairly, rather than silently exceeding it. See this task's own ``assumptions`` output for
the recommendation filed against this.
"""

from __future__ import annotations

import logging
from typing import Final

from contracts import ToolSpec

__all__ = ["MAX_TOOLS_PER_ROLE", "cap_fairly"]

_LOG = logging.getLogger(__name__)

#: The accuracy-optimal visible-set upper bound (``contracts.ToolRole``'s own docstring,
#: ADR-003). Load-bearing — do not raise without re-reading the research it cites.
MAX_TOOLS_PER_ROLE: Final[int] = 8


def cap_fairly(
    role_name: str, contributions: list[tuple[str, list[ToolSpec]]]
) -> tuple[ToolSpec, ...]:
    """Round-robin one tool at a time across ``contributions`` — ``(source name, that
    source's specs for this role, in the source's own declared order)`` pairs — until
    :data:`MAX_TOOLS_PER_ROLE` is reached or every source is exhausted, whichever comes
    first.

    Round-robin, not "take the first N in source-priority order": a role with several
    substantial contributors must never have one contributor's tools entirely excluded in
    favour of another's just because it happens to be declared first — see this module's
    docstring for the current, real example. Excluded tools are logged once, by name and
    source, never silently dropped from visibility with no trace.
    """
    queues = [(name, list(specs)) for name, specs in contributions if specs]
    total = sum(len(specs) for _name, specs in queues)
    if total <= MAX_TOOLS_PER_ROLE:
        return tuple(spec for _name, specs in queues for spec in specs)

    kept: list[ToolSpec] = []
    while queues and len(kept) < MAX_TOOLS_PER_ROLE:
        next_round: list[tuple[str, list[ToolSpec]]] = []
        for name, specs in queues:
            if len(kept) < MAX_TOOLS_PER_ROLE:
                kept.append(specs.pop(0))
            if specs:
                next_round.append((name, specs))
        queues = next_round

    excluded = [spec.name for _name, specs in queues for spec in specs]
    _LOG.warning(
        "role %r has %d declared tools across %d source(s), past the %d accuracy-optimal "
        "visible-set bound (ADR-003) — keeping %s, excluding %s from the default MCP "
        "registry. This is a cross-module coordination gap (see mcp/_cap.py's module "
        "docstring), not a defect in any one excluded source.",
        role_name, total, len(contributions), MAX_TOOLS_PER_ROLE,
        [spec.name for spec in kept], excluded,
    )
    return tuple(kept)
