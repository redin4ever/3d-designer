"""Tests for ``cache.py``: ``snapshot_of``, ``invalidate_cache``.

The whole point of caching is that ``snapshot_of`` does not re-read the engine on every
call. Per the module brief, these tests are built specifically so a no-op
``invalidate_cache`` fails — value equality alone cannot catch that bug when handlers are
deterministic, so the engine is mutated directly, bypassing ``scene`` entirely, and the
cached value is checked both before and after invalidation.
"""

from __future__ import annotations

from contracts import Transform, Vec3
from scene import Scene


def test_snapshot_of_returns_the_same_object_on_repeat_calls(engine, handlers, add_cube_op):
    """If every call re-read the engine, two back-to-back calls would still be *equal*
    (nothing changed) — this checks identity specifically, which only a real cache, not a
    coincidence of determinism, can produce."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))

    first = scene.snapshot_of("a")
    second = scene.snapshot_of("a")

    assert first is second


def test_invalidate_cache_makes_a_stale_snapshot_fresh_again(engine, handlers, add_cube_op):
    """Built so a no-op invalidate_cache fails: the engine is mutated directly, bypassing
    scene entirely, so nothing about scene's own bookkeeping would invalidate the cache on
    its own. Before invalidate_cache, snapshot_of must keep returning the stale value;
    after it, the next call must reflect the mutation. A no-op invalidate_cache passes the
    first assertion below and fails the second; a cache that does not actually cache fails
    the first."""
    scene = Scene(engine, handlers)
    scene.apply(add_cube_op("op1", "a"))
    cached = scene.snapshot_of("a")
    assert cached.transform.translation == Vec3()

    engine.set_transform("a", Transform(translation=Vec3(5.0, 0.0, 0.0)))

    still_stale = scene.snapshot_of("a")
    assert still_stale is cached
    assert still_stale.transform.translation == Vec3()

    scene.invalidate_cache("a")
    fresh = scene.snapshot_of("a")

    assert fresh is not cached
    assert fresh.transform.translation == Vec3(5.0, 0.0, 0.0)


def test_invalidating_an_object_never_cached_does_not_raise(engine, handlers):
    """A defensive no-op: apply() invalidates every object an operation's result names,
    whether or not anything had read a snapshot of it yet — invalidate_cache must accept
    that without raising, or a plain apply() with no prior snapshot_of call would break."""
    scene = Scene(engine, handlers)

    scene.invalidate_cache("never-existed")
