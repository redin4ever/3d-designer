"""Tests for ``add_railing`` — the flagship operation this library exists for (ADR-004).

The most tests in this package live here on purpose: a railing is the user's own worked
example of the product's whole premise, and the four defining properties in
``railing.py``'s module docstring (plumb posts regardless of slope, posts forced at
corners, a rail terminating at post centrelines, balusters spaced to a clear opening) are
each a documented naive-generator failure mode, not a style preference.

``add_railing`` is a throwing stub as of this file (Rule 4 — tests come first); every test
below is expected to fail with ``NotImplementedError`` until the next pass implements it.
"""

from __future__ import annotations

import math

import pytest

from contracts import EPSILON, Operation, Vec3
from ops import add_railing


def _posts(result) -> list[str]:
    return [pid for pid in result.produced_objects if "_post_" in pid]


def _balusters(result) -> list[str]:
    return [pid for pid in result.produced_objects if "_baluster_" in pid]


def test_level_path_places_the_requested_number_of_posts_all_plumb(engine) -> None:
    """A generator that gets a flat run wrong will certainly get a sloped one wrong too —
    this is the baseline case every rake case above it is a variation of. Post count is
    the requested spacing fitted along the path (both endpoints included); every post must
    stand plumb even here, where "just leave the primitive's default rotation" happens to
    look right for the wrong reason."""
    path = [Vec3(0, 0, 0), Vec3(6.0, 0, 0)]
    op = Operation(
        op_id="level_rail",
        kind="add_railing",
        params={
            "object_id": "level_rail",
            "path": path,
            "height": 0.9,
            "post_spacing": 1.5,
            "baluster_gap": 0.1,
        },
    )

    result = add_railing(engine, op)

    posts = _posts(result)
    assert len(posts) == 5, "6m path at 1.5m pitch, endpoints included, is 5 posts"

    for pid in posts:
        rotation = engine.snapshot(pid).transform.rotation
        world_up = rotation.rotate(Vec3(0, 0, 1))
        assert world_up.as_tuple() == pytest.approx((0.0, 0.0, 1.0), abs=1e-4), (
            f"{pid} is not plumb on a flat run"
        )


def test_posts_are_plumb_on_a_31_degree_rake_and_spacing_is_measured_along_the_path(
    engine,
) -> None:
    """THE flagship case. Rise 1.8 over run 3.0 is a 31-degree rake. A post normal to the
    rake — aligned to the path tangent instead of world up — is *the* single most common
    naive-generator error and is invisible in a thumbnail render. Separately: pacing posts
    by the path's horizontal run instead of its true 3D arc length under-counts them on
    any rake (4 posts here instead of 5), leaving the top of the stair without a post — a
    real, common defect this test's own sanity check below demonstrates numerically."""
    run, rise = 3.0, 1.8
    path = [Vec3(0, 0, 0), Vec3(run, 0, rise)]
    arc_length = math.hypot(run, rise)
    spacing = arc_length / 4  # exactly 5 posts, endpoints included, no remainder

    naive_count = math.floor(run / spacing) + 1
    assert naive_count == 4, "sanity: horizontal-only pacing must under-count on this rake"

    op = Operation(
        op_id="rake_rail",
        kind="add_railing",
        params={
            "object_id": "rake_rail",
            "path": path,
            "height": 0.9,
            "post_spacing": spacing,
            "baluster_gap": 0.1,
        },
    )

    result = add_railing(engine, op)

    posts = _posts(result)
    assert len(posts) == 5, (
        f"expected 5 posts measured along the {arc_length:.4f}m rake, not the {run}m "
        "horizontal run"
    )

    for pid in posts:
        rotation = engine.snapshot(pid).transform.rotation
        world_up = rotation.rotate(Vec3(0, 0, 1))
        assert world_up.as_tuple() == pytest.approx((0.0, 0.0, 1.0), abs=1e-4), (
            f"{pid} leans at the rake's own angle instead of standing plumb"
        )


def test_a_post_lands_exactly_at_an_l_shaped_corner(engine) -> None:
    """A fixed pitch with no corner resampling leaves the actual corner either short a
    post (a gap a person's hand could fit through) or straddled by two overlapping posts
    (a doubled post) — neither of which a render catches, and both of which a person
    leaning on the rail at exactly that point would find immediately."""
    corner = Vec3(4.0, 0.0, 0.0)
    path = [Vec3(0, 0, 0), corner, Vec3(4.0, 3.0, 0.0)]
    op = Operation(
        op_id="l_rail",
        kind="add_railing",
        params={
            "object_id": "l_rail",
            "path": path,
            "height": 0.9,
            "post_spacing": 1.3,  # does not land on the corner naturally from either leg
            "baluster_gap": 0.1,
        },
    )

    result = add_railing(engine, op)

    posts = _posts(result)
    positions = [engine.snapshot(pid).transform.translation for pid in posts]

    assert any((p - corner).length() < EPSILON for p in positions), (
        f"no post lands at the corner {corner.as_tuple()}; a 1.3m pitch from the start "
        "does not land there on its own"
    )


def test_top_rail_endpoints_coincide_with_first_and_last_post_centrelines(engine) -> None:
    """A rail swept at a fixed parametric interval instead of terminating at the outer
    posts overshoots or falls short of the run, leaving either a rail stub with nothing to
    fix to, or a gap at the very end of the run — precisely where a person is most likely
    to reach for the rail while still on the stair."""
    path = [Vec3(0, 0, 0), Vec3(5.0, 0, 0)]
    op = Operation(
        op_id="run_rail",
        kind="add_railing",
        params={
            "object_id": "run_rail",
            "path": path,
            "height": 0.9,
            "post_spacing": 1.25,
            "baluster_gap": 0.1,
        },
    )

    result = add_railing(engine, op)

    posts = sorted(_posts(result), key=lambda pid: engine.snapshot(pid).transform.translation.x)
    rail_id = next(pid for pid in result.produced_objects if pid.endswith("_top_rail"))

    first_post_x = engine.snapshot(posts[0]).transform.translation.x
    last_post_x = engine.snapshot(posts[-1]).transform.translation.x
    rail_bounds = engine.world_bounds(rail_id)

    assert rail_bounds.minimum.x == pytest.approx(first_post_x, abs=EPSILON)
    assert rail_bounds.maximum.x == pytest.approx(last_post_x, abs=EPSILON)


def test_baluster_clear_gap_is_surface_to_surface_not_centre_pitch(engine) -> None:
    """``baluster_gap`` names the clear opening a code-required sphere must not pass
    through. A generator that instead spaces baluster centrelines by this number produces
    a real opening wider by the balusters' own width — the exact confusion the parameter
    exists to prevent, and it passes every check that only looks at centre positions."""
    baluster_width = 0.03
    path = [Vec3(0, 0, 0), Vec3(2.0, 0, 0)]
    op = Operation(
        op_id="gap_rail",
        kind="add_railing",
        params={
            "object_id": "gap_rail",
            "path": path,
            "height": 0.9,
            "post_spacing": 2.0,
            "baluster_gap": 0.1,
            "baluster_size": (baluster_width, baluster_width),
        },
    )

    result = add_railing(engine, op)

    balusters = sorted(
        _balusters(result), key=lambda pid: engine.snapshot(pid).transform.translation.x
    )
    assert len(balusters) >= 2

    b0_bounds, b1_bounds = engine.world_bounds(balusters[0]), engine.world_bounds(balusters[1])
    clear_gap = b1_bounds.minimum.x - b0_bounds.maximum.x
    centre_pitch = (
        engine.snapshot(balusters[1]).transform.translation.x
        - engine.snapshot(balusters[0]).transform.translation.x
    )

    assert clear_gap == pytest.approx(0.1, abs=EPSILON)
    assert centre_pitch != pytest.approx(0.1, abs=1e-3), (
        "clear gap and centre-to-centre pitch must not be the same number"
    )
    assert centre_pitch == pytest.approx(0.1 + baluster_width, abs=EPSILON)


def test_add_railing_names_every_part_with_predictable_ids(engine) -> None:
    """Constraints are stored, not just applied (ADR-002) — a later pass that wants to
    ``plumb``-check or ``flush_with`` one specific baluster needs a stable id to name it
    by. An id that cannot be predicted from ``op.op_id`` and an index means that later
    pass has no target to reference at all."""
    path = [Vec3(0, 0, 0), Vec3(3.0, 0, 0)]
    op = Operation(
        op_id="named_rail",
        kind="add_railing",
        params={
            "object_id": "named_rail",
            "path": path,
            "height": 0.9,
            "post_spacing": 1.5,
            "baluster_gap": 0.1,
        },
    )

    result = add_railing(engine, op)

    assert "named_rail_post_000" in result.produced_objects
    assert "named_rail_post_001" in result.produced_objects
    assert "named_rail_top_rail" in result.produced_objects
    assert any(pid.startswith("named_rail_baluster_") for pid in result.produced_objects)
