"""Stub ``RawOps`` — arbitrary Python against the live engine context (ADR-009).

Raises. See ``src/engine/mesh.py`` for why. When implemented, ``execute`` must let a
raising ``source`` propagate its *original* exception unwrapped — the caller wraps it into
:class:`contracts.EngineError`, per the docstring on ``RawOps.execute`` in
``src/contracts/engine.py``. Catching and rewrapping here would break every call site's
wrapper, which expects the original exception as ``__cause__``.
"""

from __future__ import annotations

__all__ = ["RawOpsMixin"]


class RawOpsMixin:
    """``RawOps`` surface, mixed into :class:`~engine.session.BlenderEngine`."""

    def execute(self, source: str, namespace: dict | None = None) -> dict:
        raise NotImplementedError("engine.execute: not implemented")
