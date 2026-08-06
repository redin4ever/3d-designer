"""Conformance checks for ``solidify``, ``decimate`` and ``recalculate_normals``.

A distinct actor from ``conformance_modifiers.py``: those checks are about selection
(bevel), combination (boolean) and instancing (array); these three reshape a single mesh in
bulk with no selection argument at all. Added in response to a conformance audit — none of
the three had any check before this file.
"""

from __future__ import annotations

import pytest

from contracts import EngineProtocol, Vec3
from testing import unit_cube

__all__ = [
    "check_solidify_thickens_by_the_requested_amount",
    "check_decimate_reduces_the_polygon_count",
    "check_recalculate_normals_inside_flips_the_winding",
]


def check_solidify_thickens_by_the_requested_amount(engine: EngineProtocol) -> None:
    """A no-op or wrongly-scaled solidify is invisible in a viewport but ships a wall with
    no real thickness, or the wrong thickness, once exported and inspected up close."""
    oid = engine.create_primitive("plate", "plane", Vec3(1, 1, 0))
    before = engine.world_bounds(oid).size.z
    assert before == pytest.approx(0.0, abs=1e-6)

    engine.solidify(oid, thickness=0.2)

    after = engine.world_bounds(oid).size.z
    assert 0.1 <= after <= 0.4, f"expected roughly 0.2m of thickness, got {after}"


def check_decimate_reduces_the_polygon_count(engine: EngineProtocol) -> None:
    """A no-op decimate silently ships the full polygon count against a budget the caller
    believes was respected — a LOD request that produced no LOD at all."""
    oid = engine.create_primitive("blob", "sphere", Vec3(1, 1, 1))
    before = engine.snapshot(oid).polygon_count

    engine.decimate(oid, ratio=0.5)

    after = engine.snapshot(oid).polygon_count
    assert after < before, f"decimate(ratio=0.5) did not reduce polygon_count ({before} -> {after})"


def _face_points_inward(p0, p1, p2, centroid) -> bool:
    normal = (p1 - p0).cross(p2 - p0)
    face_centre = (p0 + p1 + p2) * (1 / 3)
    return normal.dot(centroid - face_centre) > 0


def check_recalculate_normals_inside_flips_the_winding(engine: EngineProtocol) -> None:
    """A mesh whose winding faces the wrong way renders as invisible (backface culled) or,
    fed into a later boolean or solidify, produces an inside-out result with no error
    anywhere. ``recalculate_normals(inside=True)`` is the one primitive for deliberately
    producing that; a no-op here is invisible until the render comes back wrong."""
    verts, faces = unit_cube()
    oid = engine.create_mesh("winding_box", verts, faces)
    before = engine.snapshot(oid)
    centroid = before.world_bounds().centre
    before_verts = before.world_vertices()
    assert not any(
        _face_points_inward(before_verts[a], before_verts[b], before_verts[c], centroid)
        for a, b, c in before.triangles
    ), "unit_cube() is documented as outward-wound; this check's own premise is broken"

    engine.recalculate_normals(oid, inside=True)

    after = engine.snapshot(oid)
    after_verts = after.world_vertices()
    assert all(
        _face_points_inward(after_verts[a], after_verts[b], after_verts[c], centroid)
        for a, b, c in after.triangles
    ), "recalculate_normals(inside=True) did not flip every face to point inward"
