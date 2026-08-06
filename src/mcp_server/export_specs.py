"""The two export tools, wired to real handlers (ADR-014, Gate B 4.1).

``export.EXPORT_SPECS`` declares both tools correctly and carries ``handler=None`` — as
every registry-content module does, because a handler is a *bound* thing and a spec is a
module-level constant built at import time, when no engine exists. ``dispatch`` therefore
treated them like every other handler-less mutating tool: it wrapped the call in a
``contracts.Operation`` and routed it through the operation log, which resolves the kind in
the handler registry. Export is not an operation kind and never was, so the live call
raised ``KeyError: "unknown operation kind 'export_scene'"`` — the terminal step of every
journey, and the artifact the user defined "it worked" as, had never once worked through
the agent's own path.

This module supplies what was missing: the same two specs, re-issued with a handler that
runs ``export.export_scene`` directly against the engine, **outside** the log. An export
produces no geometry, so a log entry for it is one undo could only treat as a no-op.

Attaching the handler here rather than in ``export/registry.py`` is not a boundary dodge
(Rule 5 — that module is sibling-owned): a handler needs the live engine, which no
module-level constant anywhere can have. The engine arrives at call time through
``context.needs``, and *which* execution path a tool takes is registry policy, which is
this module's job.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Sequence

from contracts import AssetClass, ExportReport, ToolError, ToolSpec, profile_for
from export import EXPORT_SPECS, banner_for, check_budget, export_scene

from .context import needs
from .serialize import to_jsonable

__all__ = ["EXPORT_TOOL_SPECS", "run_export"]


def _asset_class(value: str | None) -> AssetClass | None:
    """Coerce the JSON string an agent sends into the enum ``export`` expects.

    ``app`` owns JSON->domain coercion for operation params; a directly-dispatched handler
    never passes through it, so this one field is coerced here. Failing by name matters:
    ``AssetClass("hero")`` raises a bare ``ValueError`` that tells the agent nothing about
    the five names that would have worked.
    """
    if value is None or value == "":
        return None
    try:
        return AssetClass(value)
    except ValueError as exc:
        known = ", ".join(member.value for member in AssetClass)
        raise ToolError(
            rule="export.unknown_asset_class",
            detail=f"{value!r} is not an asset class",
            suggestion=f"use one of: {known}, or omit it to check the profile's hard ceiling",
        ) from exc


def _profile(name: str):
    """``contracts.profile_for`` raises a bare ``KeyError`` on an unknown profile. Reaching
    an agent as a traceback that is exactly the opaque failure Gate A 4.2 asked about — it
    retries the same call instead of picking a profile that exists."""
    try:
        return profile_for(name)
    except KeyError as exc:
        raise ToolError(
            rule="export.unknown_profile",
            detail=f"no export profile named {name!r}",
            suggestion=str(exc.args[0] if exc.args else "known profiles: roblox, unity, unreal, godot"),
        ) from exc


def run_export(
    engine: Any,
    object_ids: Sequence[str],
    path: str,
    *,
    profile_name: str = "roblox",
    asset_class: str | None = None,
    force: bool = False,
) -> ExportReport:
    """The real work, returning the real :class:`contracts.ExportReport`.

    Separate from the registered handler so the report itself — not a serialised copy of it
    — is what this module produces, and so a caller inside the process can have the typed
    value rather than the wire form.
    """
    _profile(profile_name)  # named refusal before anything is written
    return export_scene(
        engine,
        list(object_ids),
        path,
        profile_name=profile_name,
        asset_class=_asset_class(asset_class),
        force=force,
    )


@needs("engine")
def _export_scene_handler(
    *,
    engine: Any,
    object_ids: Sequence[str],
    path: str,
    profile_name: str = "roblox",
    asset_class: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Write the file and hand back the report **with its banner**.

    ``ExportReport.banner`` is a property, and ``to_jsonable`` walks dataclass *fields* on
    purpose — a serialiser that evaluated properties would run arbitrary computation while
    encoding a response. So the banner is attached explicitly here, because it is the one
    line a person can act on (Gate A 6.3: export always writes, and says what is wrong).
    """
    report = run_export(
        engine, object_ids, path,
        profile_name=profile_name, asset_class=asset_class, force=force,
    )
    return {**to_jsonable(report), "banner": banner_for(report)}


@needs("engine")
def _check_export_budget_handler(
    *,
    engine: Any,
    object_ids: Sequence[str],
    profile_name: str = "roblox",
    asset_class: str | None = None,
) -> dict[str, Any]:
    """Answer the budget question without writing anything.

    Reports the overage rather than refusing on it — Gate A 6.3 chose report-over-block, and
    an agent that is told *by how much* it is over has a decimation ratio to aim at, where
    one told only "too heavy" has to guess.
    """
    profile = _profile(profile_name)
    selected = _asset_class(asset_class)
    defects = check_budget(engine, list(object_ids), profile, selected)

    per_object = [
        {"object_id": oid, "triangles": engine.snapshot(oid).triangle_count}
        for oid in object_ids
    ]
    total = sum(entry["triangles"] for entry in per_object)
    budget = (
        profile.budgets.get(selected) if selected is not None else profile.max_triangles_per_mesh
    )
    over_by = int(max((defect.magnitude or 0.0) for defect in defects)) if defects else 0

    if not defects:
        banner = (
            f"{total} tris across {len(per_object)} object(s) — within the {profile.name} "
            f"budget ({budget if budget is not None else 'no ceiling declared'})."
        )
    else:
        worst = ", ".join(f"{d.object_id} by {d.magnitude:.0f}" for d in defects[:8])
        banner = (
            f"{len(defects)} object(s) over the {profile.name} budget of {budget}: {worst}"
            + (" ..." if len(defects) > 8 else "")
        )

    return {
        "profile": profile.name,
        "asset_class": selected.value if selected is not None else None,
        "objects": per_object,
        "total_triangles": total,
        "budget": budget,
        "over_budget_by": over_by,
        "defects": to_jsonable(defects),
        "banner": banner,
    }


_HANDLERS = {
    "export_scene": _export_scene_handler,
    "check_export_budget": _check_export_budget_handler,
}

EXPORT_TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    dataclasses.replace(spec, handler=_HANDLERS[spec.name]) if spec.name in _HANDLERS else spec
    for spec in EXPORT_SPECS
)
"""``export.EXPORT_SPECS`` with the handlers attached. Description, schema, roles and the
mutating flag all stay exactly as ``export`` declared them — content is that module's, and
only the execution route is decided here."""
