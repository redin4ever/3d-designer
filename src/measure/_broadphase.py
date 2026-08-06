"""Uniform-grid broad phase over one mesh's own triangles.

``find_self_intersections`` compared every triangle against every other one: 6.5s on the
960-triangle sphere Blender builds in 0.006s, finding nothing, on a check that runs
automatically after every geometry change. This file is the pruning step that makes it
proportional to the mesh rather than to its square.

**Why not** :class:`spatial.SpatialIndex`. That index is the right structure one level up
— it is keyed by object id and every entry it resolves comes from
``engine.world_bounds(object_id)``, so putting a mesh's triangles in it means fabricating a
fake engine with one object per triangle. Worse, it would not fix this: its
``pairs_overlapping`` is a flat scan over every unordered pair, which measures 0.06s on 960
boxes and 6s again at 10 000. It is used, as intended, for the object-level neighbour
queries in ``measure/neighbours.py``. Intra-mesh triangle pruning needs a structure that is
sub-quadratic in the count, which is this one.

**The correctness contract, which is not negotiable for speed** (a missed
self-intersection is a BLOCKER the agent then exports): :func:`candidate_pairs` returns a
*superset* of every pair whose boxes overlap. Two triangles that genuinely intersect share
a point, so their boxes overlap on all three axes; that shared point lies in exactly one
cell, and both boxes are inserted into every cell they touch — so the pair is always
generated. Every fallback in this file falls back to *more* work, never less.
"""

from __future__ import annotations

import math
from typing import Sequence

from contracts import Vec3

__all__ = ["triangle_boxes", "candidate_pairs", "GRID_MIN_TRIANGLES", "MAX_CELLS_PER_TRIANGLE"]

#: ``(min_x, min_y, min_z, max_x, max_y, max_z)``. Plain floats rather than
#: :class:`contracts.AABB`: this is the innermost loop of the check, run once per triangle
#: and again per candidate pair, and the box here is never handed to anything outside this
#: file. ``AABB`` stays the type at every public boundary.
Box = tuple[float, float, float, float, float, float]

#: Below this, the grid costs more to build than the sweep costs to run, and every mesh in
#: this suite's older tests is smaller than it. Under this count every pair is returned —
#: identical work to before this file existed, so small-mesh behaviour cannot regress.
GRID_MIN_TRIANGLES = 64

#: A triangle spanning more cells than this is held out of the grid and paired against
#: everything instead. One ground-plane triangle among ten thousand small ones would
#: otherwise force the cell size up until the grid stopped pruning anything.
MAX_CELLS_PER_TRIANGLE = 27


def triangle_boxes(
    vertices: Sequence[Vec3], triangles: Sequence[tuple[int, int, int]]
) -> list[Box]:
    """One axis-aligned box per triangle, in triangle order."""
    boxes: list[Box] = []
    for i, j, k in triangles:
        a, b, c = vertices[i], vertices[j], vertices[k]
        boxes.append(
            (
                min(a.x, b.x, c.x), min(a.y, b.y, c.y), min(a.z, b.z, c.z),
                max(a.x, b.x, c.x), max(a.y, b.y, c.y), max(a.z, b.z, c.z),
            )
        )
    return boxes


def _boxes_overlap(a: Box, b: Box) -> bool:
    return (
        a[0] <= b[3] and a[3] >= b[0]
        and a[1] <= b[4] and a[4] >= b[1]
        and a[2] <= b[5] and a[5] >= b[2]
    )


def _cell_size(boxes: Sequence[Box]) -> float:
    """Twice the median triangle's largest extent, so a typical triangle touches at most
    two cells per axis.

    Median rather than mean on purpose: one 200 m ground plane among 10 000 hand-sized
    triangles drags a mean far enough that the grid degenerates to a single cell, which is
    the n^2 sweep again wearing a dictionary. Outliers are handled by
    :data:`MAX_CELLS_PER_TRIANGLE` instead, where they cost only themselves.
    """
    extents = sorted(max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) for b in boxes)
    return 2.0 * extents[len(extents) // 2]


def _cells_of(box: Box, cell: float) -> tuple[int, int, int, int, int, int]:
    return (
        math.floor(box[0] / cell), math.floor(box[1] / cell), math.floor(box[2] / cell),
        math.floor(box[3] / cell), math.floor(box[4] / cell), math.floor(box[5] / cell),
    )


def _all_pairs(count: int) -> tuple[tuple[int, int], ...]:
    return tuple((i, j) for i in range(count) for j in range(i + 1, count))


def candidate_pairs(boxes: Sequence[Box]) -> tuple[tuple[int, int], ...]:
    """Every ``(i, j)``, ``i < j``, whose boxes could touch — ascending, deduplicated.

    A superset of the truly-intersecting pairs, never a subset. See this module's
    docstring for why that holds, including for the two fallbacks (a mesh too small to be
    worth a grid, and a mesh whose triangles are all degenerate points).
    """
    count = len(boxes)
    if count < GRID_MIN_TRIANGLES:
        return _all_pairs(count)

    cell = _cell_size(boxes)
    if not cell > 0.0 or not math.isfinite(cell):
        return _all_pairs(count)

    grid: dict[tuple[int, int, int], list[int]] = {}
    oversized: list[int] = []
    for index, box in enumerate(boxes):
        lox, loy, loz, hix, hiy, hiz = _cells_of(box, cell)
        spanned = (hix - lox + 1) * (hiy - loy + 1) * (hiz - loz + 1)
        if spanned > MAX_CELLS_PER_TRIANGLE:
            oversized.append(index)
            continue
        for cx in range(lox, hix + 1):
            for cy in range(loy, hiy + 1):
                for cz in range(loz, hiz + 1):
                    grid.setdefault((cx, cy, cz), []).append(index)

    pairs: set[tuple[int, int]] = set()
    for bucket in grid.values():
        for slot, i in enumerate(bucket):
            box_i = boxes[i]
            for j in bucket[slot + 1 :]:
                if _boxes_overlap(box_i, boxes[j]):
                    pairs.add((i, j))

    # A held-out triangle is compared with everything, box-checked. It pays for its own
    # size and nothing else pays for it.
    for i in oversized:
        box_i = boxes[i]
        for j in range(count):
            if i != j and _boxes_overlap(box_i, boxes[j]):
                pairs.add((min(i, j), max(i, j)))

    return tuple(sorted(pairs))
