"""The per-object geometry cache: ``snapshot_of``, ``invalidate_cache``.

Reading geometry through the engine is not free at thousands of objects (ADR-011), so
``scene`` caches one ``MeshSnapshot`` per object id and only re-reads on an explicit
invalidation — which ``document.py``'s ``apply`` calls for every object an operation
touches, and ``document.py``'s ``replay`` calls in bulk (``self._cache.clear()``) before
rebuilding everything from nothing.
"""

from __future__ import annotations

from contracts import MeshSnapshot

__all__ = ["CacheMixin"]


class CacheMixin:
    """``snapshot_of``/``invalidate_cache``. Expects ``self._cache: dict[str,
    MeshSnapshot]`` and ``self._engine`` — see ``scene/__init__.py``."""

    def snapshot_of(self, object_id: str) -> MeshSnapshot:
        """Return the cached snapshot for ``object_id``, reading the engine only on a
        cache miss.

        Once implemented: if ``object_id in self._cache``, return the cached value as
        stored — the same Python object, not a copy, so two calls with nothing
        invalidated in between return identical objects (``x is y``), not merely equal
        ones. Otherwise call ``self._engine.snapshot(object_id)``, store the result in
        ``self._cache``, and return it.

        A no-op implementation of :meth:`invalidate_cache` is invisible to a test that
        only checks value equality after a change, because the fake handlers used in
        this package's tests are deterministic and would often compute the same value
        again anyway. The cache is instead tested by mutating engine state *without*
        going through an operation (bypassing invalidation entirely) and checking the
        stale value keeps coming back until ``invalidate_cache`` is called. See
        ``cache_test.py::test_invalidate_cache_makes_a_stale_snapshot_fresh_again``.
        """
        if object_id in self._cache:
            return self._cache[object_id]
        snapshot = self._engine.snapshot(object_id)
        self._cache[object_id] = snapshot
        return snapshot

    def invalidate_cache(self, object_id: str) -> None:
        """Drop ``object_id`` from the cache, if present.

        Once implemented: ``self._cache.pop(object_id, None)`` — never raise for an id
        that was never cached, or was already invalidated. Called defensively from
        ``document.py``'s ``apply`` for every object an operation's ``OperationResult``
        names, whether or not a snapshot had actually been read for it yet.
        """
        self._cache.pop(object_id, None)
