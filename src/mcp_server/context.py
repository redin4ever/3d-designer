"""How a handler declared *here* reaches the live session.

Registry content modules (``ops``, ``gaps``, ``align``, ``uv``) leave execution to the
operation log, so their specs carry ``handler=None`` and ``dispatch`` builds an
``Operation`` for them. Two kinds of tool cannot work that way — export, which writes a
file and produces no geometry (ADR-014), and the session tools, which report on the phase
and the registry rather than on the model. Both carry a real ``ToolSpec.handler``.

A handler is a plain function attached to a module-level ``ToolSpec`` constant, built at
import time, when no engine and no orchestrator exist yet. It gets them at *call* time
instead: it declares what it needs with :func:`needs`, and ``dispatch`` supplies exactly
that alongside the caller's params. Declared rather than inferred, because a handler that
silently accepts an ``engine`` keyword it never asked for is one whose signature no longer
says what it does.

Not part of ``mcp_server``'s public barrel — exercised through ``dispatch``.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from contracts import ToolError

__all__ = ["needs", "context_for", "engine_of"]

_ATTR = "forge3d_context"

_F = TypeVar("_F", bound=Callable[..., Any])


def needs(*names: str) -> Callable[[_F], _F]:
    """Declare which pieces of the live session this handler wants: ``"engine"``,
    ``"orchestrator"``, or both. They arrive as keyword arguments of the same name."""
    unknown = set(names) - {"engine", "orchestrator"}
    if unknown:
        raise ValueError(f"unknown handler context {sorted(unknown)}; known: engine, orchestrator")

    def decorate(fn: _F) -> _F:
        setattr(fn, _ATTR, tuple(names))
        return fn

    return decorate


def engine_of(orchestrator: Any) -> Any:
    """The engine behind the orchestrator's scene.

    ``ScenePort.engine`` is the declared route (it was added to close B-000, so that
    measurement had somewhere real to read geometry from). ``Orchestrator`` itself does not
    re-export it, and reaching through ``_scene`` is a private attribute of a module this
    one may not edit — so this tries the public shapes first and the private one last, and
    fails by name rather than with ``AttributeError`` five frames deep.
    """
    for holder in (orchestrator, getattr(orchestrator, "scene", None), getattr(orchestrator, "_scene", None)):
        engine = getattr(holder, "engine", None)
        if engine is not None:
            return engine
    raise ToolError(
        rule="mcp.engine_unreachable",
        detail=(
            "this tool reads geometry, and no engine was reachable from the orchestrator "
            "(tried .engine, .scene.engine, ._scene.engine)"
        ),
        suggestion=(
            "construct the orchestrator with a scene that exposes .engine — app.build_app "
            "already does; a bare test double may not"
        ),
    )


def context_for(handler: Any, orchestrator: Any) -> dict[str, Any]:
    """The keyword arguments ``handler`` declared with :func:`needs`. Empty for any handler
    that declared nothing, which is every handler a content module attaches."""
    wanted: tuple[str, ...] = getattr(handler, _ATTR, ())
    if not wanted:
        return {}
    supplied: dict[str, Any] = {}
    if "orchestrator" in wanted:
        supplied["orchestrator"] = orchestrator
    if "engine" in wanted:
        supplied["engine"] = engine_of(orchestrator)
    return supplied
