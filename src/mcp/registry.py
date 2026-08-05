"""Registry composition — collects every ``ToolSpec`` the product declares and partitions
it by :class:`contracts.ToolRole` (ADR-003).

Registry *content* lives beside each operation (``ops.OP_SPECS``, ``export.EXPORT_SPECS``,
``raw.RAW_TOOL_SPEC``, and whatever ``measure``/``gaps``/``align``/``uv``/``detail``
eventually publish); registry *policy* — which roles see what, and how many tools that
ends up being — lives here (``.pipeline/modules.json``'s own note on this module).

Nothing here computes anything yet — every function raises until the next pass replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

import importlib
import logging
from typing import Final

from contracts import ToolRole, ToolSpec
from export import EXPORT_SPECS
from ops import OP_SPECS
from raw import RAW_TOOL_SPEC

from ._cap import cap_fairly

_LOG = logging.getLogger(__name__)

__all__ = ["build_registry", "tools_for"]

#: (module name, constant name) for sibling modules whose tool content may not exist yet
#: (``.pipeline/modules.json`` lists ``align``/``gaps``/``uv`` "planned" at the time this
#: was written; ``measure`` and ``detail`` exist but do not yet publish a ``*_SPECS``
#: constant). Order here is also round-robin priority when a role's combined tool count
#: needs capping — see ``_cap.py``.
_OPTIONAL_SOURCES: Final[tuple[tuple[str, str], ...]] = (
    ("measure", "MEASURE_SPECS"),
    ("gaps", "GAPS_SPECS"),
    ("align", "ALIGN_SPECS"),
    ("uv", "UV_SPECS"),
    ("detail", "DETAIL_SPECS"),
)


def _load_optional(module_name: str, attr_name: str) -> tuple[ToolSpec, ...]:
    """A sibling module's ``*_SPECS`` tuple, or ``()`` when it does not exist as a package
    yet (``ImportError``), exists but has not published the constant yet
    (``AttributeError``), or — these five modules are, as of this task, still being built
    concurrently by separate agents (Rule 5) — exists on disk but is genuinely mid-edit and
    momentarily invalid Python (``SyntaxError`` and friends) at the exact moment this
    collects from it. None of that may crash registry construction for every other tool at
    once, so this catches broadly and logs loudly rather than narrowly and silently."""
    try:
        module = importlib.import_module(module_name)
        return tuple(getattr(module, attr_name))
    except (ImportError, AttributeError):
        return ()
    except Exception:
        _LOG.warning(
            "mcp.registry: %s.%s could not be loaded — treating it as not-yet-available "
            "rather than crashing registry construction for every other tool.",
            module_name, attr_name, exc_info=True,
        )
        return ()


def _sources(*, include_raw: bool) -> list[tuple[str, tuple[ToolSpec, ...]]]:
    """Every content source, named, in the fixed priority order ``cap_fairly`` round-robins
    across when a role's combined count needs trimming."""
    sources: list[tuple[str, tuple[ToolSpec, ...]]] = [("ops", OP_SPECS), ("export", EXPORT_SPECS)]
    for module_name, attr_name in _OPTIONAL_SOURCES:
        specs = _load_optional(module_name, attr_name)
        if specs:
            sources.append((module_name, specs))
    if include_raw:
        sources.append(("raw", (RAW_TOOL_SPEC,)))
    return sources


def build_registry(*, include_raw: bool = True) -> dict[ToolRole, tuple[ToolSpec, ...]]:
    """Collect every declared ``ToolSpec`` and partition it by role.

    ``include_raw`` defaults to ``True`` — the raw-execution escape hatch (ADR-009) ships
    on by default, matching every other tool, but must be switchable off (e.g. a
    deployment that never wants :attr:`contracts.ToolRole.ADMIN` to reach unrestricted
    code execution) without editing this module.

    Within a role, the accuracy-optimal 8-tool visible-set bound (ADR-003) is enforced by
    ``cap_fairly`` — see ``_cap.py`` for why a role can exceed that bound in the first
    place (several sibling modules independently, correctly, declaring the same role) and
    how trimming stays fair across contributors rather than favouring whichever module's
    tools happen to be collected first.
    """
    by_role_by_source: dict[ToolRole, list[tuple[str, list[ToolSpec]]]] = {
        role: [] for role in ToolRole
    }
    for source_name, specs in _sources(include_raw=include_raw):
        per_role: dict[ToolRole, list[ToolSpec]] = {}
        for spec in specs:
            for role in spec.roles:
                per_role.setdefault(role, []).append(spec)
        for role, role_specs in per_role.items():
            by_role_by_source[role].append((source_name, role_specs))

    return {
        role: cap_fairly(role.value, contributions)
        for role, contributions in by_role_by_source.items()
    }


_DEFAULT_REGISTRY: dict[ToolRole, tuple[ToolSpec, ...]] = build_registry()


def tools_for(role: ToolRole) -> tuple[ToolSpec, ...]:
    """The tools visible to ``role`` in the default registry (``include_raw=True`` — see
    ``build_registry``). Computed once at import time: every source this collects from is
    static, constructed data, so there is nothing to gain from recomputing per call."""
    return _DEFAULT_REGISTRY[role]
