"""``RawOps`` — arbitrary Python against the live engine context (ADR-009).

``execute`` must let a raising ``source`` propagate its *original* exception unwrapped — the
caller wraps it into :class:`contracts.EngineError`, per the docstring on ``RawOps.execute``
in ``src/contracts/engine.py``. No ``try``/``except`` here, deliberately: catching and
rewrapping would break every call site's own wrapper, which expects the original exception
as ``__cause__``.
"""

from __future__ import annotations

__all__ = ["RawOpsMixin"]


class RawOpsMixin:
    """``RawOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def execute(self, source: str, namespace: dict | None = None) -> dict:
        ns = dict(namespace or {})
        ns.setdefault("engine", self)
        exec(source, ns)  # noqa: S102 — ADR-009: unrestricted by explicit decision
        return ns
