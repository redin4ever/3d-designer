"""Conformance checks for ``boolean``'s ``difference`` and ``intersect`` modes, and solver
threading.

The existing ``union`` check lives in ``conformance_modifiers.py``; these were added in
response to a conformance audit that found ``difference``/``intersect`` completely
uncovered. Split into a new file rather than grown onto ``conformance_modifiers.py``
because it mixes all three registries (universal, Blender-only, fake-only) and deserves its
own explanation of which is which and why:

- The universal checks only assert what ``FakeEngine`` actually guarantees for these two
  modes: the cutter is consumed, the target survives. ``FakeEngine.boolean`` is explicit
  that it exists "to exercise placement, measurement and bookkeeping" — for ``difference``
  it does not touch target geometry at all, and for ``intersect`` it truncates the face
  list without touching vertices, so bounds do not shrink to the true CSG result. Asserting
  real geometric bounds against that would fail on the fake for reasons that have nothing
  to do with whether ``BlenderEngine`` is correct.
- The Blender-only checks assert what an actual CSG solver must guarantee geometrically:
  difference never grows the target's extent, and intersect's bounds equal the exact
  geometric overlap. Both are true only for a real solver.
- The fake-only check asserts on ``engine.calls`` — the recorded solver argument — because
  two axis-aligned unit cubes cannot show a *geometric* difference between ``fast``,
  ``exact`` and ``manifold``, so the only way to catch a solver silently coerced to a fixed
  default is to inspect what was actually passed through. ``BlenderEngine`` has no
  equivalent introspection, so this cannot run against it.
"""

from __future__ import annotations

from contracts import EngineProtocol, Transform, Vec3

__all__ = [
    "check_boolean_difference_removes_the_cutter",
    "check_boolean_intersect_removes_the_cutter",
    "check_boolean_difference_bounds_stay_within_the_original_target",
    "check_boolean_intersect_matches_the_geometric_overlap_bounds",
    "check_boolean_solver_choice_is_threaded_through",
]


def _two_overlapping_cubes(engine: EngineProtocol, prefix: str):
    a = engine.create_primitive(f"{prefix}_a", "cube", Vec3(2, 2, 2))
    b = engine.create_primitive(
        f"{prefix}_b", "cube", Vec3(2, 2, 2), Transform(translation=Vec3(1, 0, 0))
    )
    return a, b


# ------------------------------------------------------------------------------ universal

def check_boolean_difference_removes_the_cutter(engine: EngineProtocol) -> None:
    """difference must consume the cutter like every other boolean mode — a caller that
    forgets this ends up with the cutter rendering a second time and double-counting in a
    polygon budget."""
    a, b = _two_overlapping_cubes(engine, "diff")

    engine.boolean(a, b, mode="difference", solver="exact")

    assert not engine.exists(b)
    assert engine.exists(a)
    assert engine.snapshot(a).vertex_count > 0


def check_boolean_intersect_removes_the_cutter(engine: EngineProtocol) -> None:
    """Same failure mode as the difference check above, for the third boolean mode."""
    a, b = _two_overlapping_cubes(engine, "isect")

    engine.boolean(a, b, mode="intersect", solver="exact")

    assert not engine.exists(b)
    assert engine.exists(a)
    assert engine.snapshot(a).vertex_count > 0


# --------------------------------------------------------------------------- Blender-only

def check_boolean_difference_bounds_stay_within_the_original_target(
    engine: EngineProtocol,
) -> None:
    """Blender-only: cutting material away can never make a solid bigger. FakeEngine's
    ``difference`` does not touch target geometry at all (see module docstring), so this
    bounds property is true of it only by accident, not by anything worth testing; a real
    CSG solver must guarantee it."""
    a, b = _two_overlapping_cubes(engine, "diffbounds")
    before = engine.world_bounds(a)

    engine.boolean(a, b, mode="difference", solver="exact")

    after = engine.world_bounds(a)
    for axis in ("x", "y", "z"):
        assert getattr(after.minimum, axis) >= getattr(before.minimum, axis) - 1e-6
        assert getattr(after.maximum, axis) <= getattr(before.maximum, axis) + 1e-6


def check_boolean_intersect_matches_the_geometric_overlap_bounds(
    engine: EngineProtocol,
) -> None:
    """Blender-only: for two overlapping axis-aligned cubes the intersection is itself an
    axis-aligned box with an exact, unambiguous bounding box. FakeEngine's ``intersect``
    truncates the face list without touching vertices (see module docstring), so its bounds
    do not shrink to this value at all — only a real CSG solver can satisfy this."""
    a, b = _two_overlapping_cubes(engine, "isectbounds")
    bounds_a, bounds_b = engine.world_bounds(a), engine.world_bounds(b)

    engine.boolean(a, b, mode="intersect", solver="exact")

    result = engine.world_bounds(a)
    for axis in ("x", "y", "z"):
        expected_min = max(getattr(bounds_a.minimum, axis), getattr(bounds_b.minimum, axis))
        expected_max = min(getattr(bounds_a.maximum, axis), getattr(bounds_b.maximum, axis))
        assert abs(getattr(result.minimum, axis) - expected_min) < 1e-4
        assert abs(getattr(result.maximum, axis) - expected_max) < 1e-4


# ------------------------------------------------------------------------------ fake-only

def check_boolean_solver_choice_is_threaded_through(engine: EngineProtocol) -> None:
    """Fake-only: two trivial overlapping cubes cannot show a *geometric* difference
    between solvers, so ``engine.calls`` — the recorded argument — is the only observable
    proof a solver choice was not silently coerced to a fixed default. This is exactly the
    legitimate use of ``.calls`` the fake's own docstring reserves for cases where the
    geometric outcome cannot show the difference; ``BlenderEngine`` has no equivalent
    introspection, so this check cannot run against it."""
    a1, b1 = _two_overlapping_cubes(engine, "solv1")
    a2, b2 = _two_overlapping_cubes(engine, "solv2")

    engine.boolean(a1, b1, mode="union", solver="fast")
    engine.boolean(a2, b2, mode="union", solver="manifold")

    calls = [c for c in engine.calls if c[0] == "boolean"]
    solver_by_target = {c[1][0]: c[1][3] for c in calls}
    assert solver_by_target[a1] == "fast"
    assert solver_by_target[a2] == "manifold"
