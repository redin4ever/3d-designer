"""Registry composition — collects every ``ToolSpec`` the product declares and partitions
it by :class:`contracts.ToolRole` (ADR-003).

Registry *content* lives beside each operation (``ops.OP_SPECS``, ``export.EXPORT_SPECS``,
``raw.RAW_TOOL_SPEC``, and whatever ``measure``/``gaps``/``align``/``uv``/``detail``
publish); registry *policy* — which roles see what, how execution is routed, and how many
tools that ends up being — lives here.

Two of those sources are policy decisions rather than plain collection, and both are
deliberate:

- ``export_specs.EXPORT_TOOL_SPECS`` is ``export``'s own two specs re-issued with a real
  handler, so ``dispatch`` runs them directly against the engine instead of through the
  operation log (ADR-014). Nothing about the *content* changes.
- ``session_specs.SESSION_SPECS`` is declared here because it reports on the phase and on
  this registry, and no operation module owns either (Gate B 3.1).

**Nothing here caps, trims or hides a tool.** A ``_cap.py`` used to round-robin each role
down to eight and log what it dropped, and it silently hid ``repair``, ``make_plumb`` and
``close_visual_gap`` — three core operations — from every agent that would have called
them. Asked at Gate B 3.3 whether to split roles further, hide tools, or exceed the
5-8 accuracy band and measure it, the user chose **exceed it and measure**. So an
over-subscribed role is *recorded* (``registry_test.py`` pins every role's count, and
``README.md`` states which roles are over) and logged, never trimmed. The real fix for
``REFINE``'s 19 tools was splitting ``REPAIR`` and ``ALIGN`` out of it, which
``contracts.ToolRole`` has now done; capping was the symptom.
"""

from __future__ import annotations

import importlib
import logging
from typing import Final

from contracts import ToolRole, ToolSpec
from ops import OP_SPECS
from raw import RAW_TOOL_SPEC

from .export_specs import EXPORT_TOOL_SPECS
from .session_specs import SESSION_SPECS

_LOG = logging.getLogger(__name__)

__all__ = ["build_registry", "tools_for"]

#: The accuracy-optimal visible-set band (``contracts.ToolRole``'s own docstring, ADR-003).
#: Guidance derived from other systems, not law here — Gate B 3.3. Crossing it is logged so
#: the decision stays measured rather than assumed; it is never enforced.
ACCURACY_BAND_MAX: Final[int] = 8

#: (module name, constant name) for sibling modules whose tool content may not exist yet.
#: ``measure`` and ``detail`` exist but do not publish a ``*_SPECS`` constant at the time
#: this was written.
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
    (``AttributeError``), or — these modules are built concurrently by separate agents
    (Rule 5) — exists on disk but is genuinely mid-edit and momentarily invalid Python
    (``SyntaxError`` and friends) at the exact moment this collects from it. None of that
    may crash registry construction for every other tool at once, so this catches broadly
    and logs loudly rather than narrowly and silently."""
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
    """Every content source, named, in declaration order."""
    sources: list[tuple[str, tuple[ToolSpec, ...]]] = [
        ("ops", OP_SPECS),
        ("export", EXPORT_TOOL_SPECS),
        ("session", SESSION_SPECS),
    ]
    for module_name, attr_name in _OPTIONAL_SOURCES:
        specs = _load_optional(module_name, attr_name)
        if specs:
            sources.append((module_name, specs))
    if include_raw:
        sources.append(("raw", (RAW_TOOL_SPEC,)))
    return sources


def _record_visible_set_size(by_role: dict[ToolRole, tuple[ToolSpec, ...]]) -> None:
    """Say so, loudly, when a role's visible set passes the accuracy band.

    Recording rather than capping is the whole of Gate B 3.3. The one thing this must never
    do is make the number go away — a fallback that trimmed the set to keep it under eight
    is what hid three core operations from every agent, with every suite green.
    """
    over = {
        role.value: len(specs)
        for role, specs in by_role.items()
        if len(specs) > ACCURACY_BAND_MAX
    }
    if over:
        _LOG.warning(
            "mcp.registry: %s past the %d-tool accuracy band (ADR-003). Kept in full and "
            "recorded, not trimmed — Gate B 3.3 chose to exceed the band and measure it. "
            "No tool is hidden.",
            over, ACCURACY_BAND_MAX,
        )


def build_registry(*, include_raw: bool = True) -> dict[ToolRole, tuple[ToolSpec, ...]]:
    """Collect every declared ``ToolSpec`` and partition it by role.

    ``include_raw`` defaults to ``True`` — the raw-execution escape hatch (ADR-009) ships on
    by default, matching every other tool, but must be switchable off (e.g. a deployment
    that never wants :attr:`contracts.ToolRole.ADMIN` to reach unrestricted code execution)
    without editing this module.

    Every declared tool reaches every role that declares it. See this module's docstring for
    why that sentence needs saying.
    """
    by_role: dict[ToolRole, list[ToolSpec]] = {role: [] for role in ToolRole}
    for _source_name, specs in _sources(include_raw=include_raw):
        for spec in specs:
            for role in spec.roles:
                by_role[role].append(spec)

    registry = {role: tuple(specs) for role, specs in by_role.items()}
    _record_visible_set_size(registry)
    return registry


_DEFAULT_REGISTRY: dict[ToolRole, tuple[ToolSpec, ...]] = build_registry()


def tools_for(role: ToolRole) -> tuple[ToolSpec, ...]:
    """The tools visible to ``role`` in the default registry (``include_raw=True`` — see
    ``build_registry``). Computed once at import time: every source this collects from is
    static, constructed data, so there is nothing to gain from recomputing per call."""
    return _DEFAULT_REGISTRY[role]
