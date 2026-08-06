"""2D simple-polygon triangulation, scored by triangle aspect ratio.

Private to ``detail`` — ``topology.py`` is the only importer. It exists as its own file
because it is a distinct decision (Rule 2 seam #1): *given a flat polygon, which triangles*,
with no notion of a mesh, an engine, a bevel or a vertex id anywhere in it. That makes it
testable through ``retriangulate_planar_regions`` on hand-built shapes and keeps
``topology.py`` about mesh topology rather than about computational geometry.

**Why three strategies and not one.** Measured against real Blender bevel output (F-018):
greedy ear clipping alone left the mean aspect ratio at 83.5, the O(n^3) dynamic program
alone at 90.8, and neither beat the triangulation Blender had already produced on two thirds
of the regions. Taking the best-scoring of {what we were given, ear clip, dynamic program},
each optionally improved by edge flips, reached 64.2 — because the strategies fail on
*different* shapes. The cost is three cheap passes over polygons that are almost always
under a dozen vertices.

Everything here is deterministic: no set iteration decides an outcome, ties break on the
lowest index, and the flip pass walks its edges in sorted order. Replay depends on it
(ADR-002).
"""

from __future__ import annotations

import math

__all__ = ["aspect_ratio", "best_triangulation", "signed_area", "MAX_EAR_CLIP", "MAX_DP"]

Point = tuple[float, float]
Tri = tuple[int, int, int]

#: Polygons above this many boundary vertices are declined outright. The search is cubic in
#: boundary length, and an unattended phase that stalls for minutes on one floor slab is a
#: worse failure than a slightly slivery floor slab — Rule 6 treats a stall as a death.
MAX_EAR_CLIP = 96

#: The dynamic program is cubic with a heavier constant, so it gets a tighter bound. Bevel
#: output regions are almost always under a dozen vertices; this only ever declines the
#: outliers, and ear clipping still runs on them.
MAX_DP = 40


def aspect_ratio(a: Point, b: Point, c: Point) -> float:
    """Longest side over shortest side. ``1.0`` is equilateral, ``inf`` is degenerate."""
    sides = sorted((math.dist(a, b), math.dist(b, c), math.dist(c, a)))
    return sides[2] / sides[0] if sides[0] > 1e-12 else math.inf


def signed_area(pts: list[Point]) -> float:
    """Twice the signed area. Positive means counter-clockwise."""
    total = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _score(pts: list[Point], tris: list[Tri]) -> float:
    """Total aspect ratio. Minimising the sum is minimising the mean over a fixed count."""
    return sum(aspect_ratio(pts[i], pts[j], pts[k]) for i, j, k in tris)


def _epsilon(pts: list[Point]) -> float:
    """An area tolerance scaled to the polygon, not an absolute one.

    A fixed epsilon is wrong at both ends here: bevel corner triangles are sub-millimetre
    while floor slabs are tens of metres, and the same constant would treat one as degenerate
    or the other as non-degenerate.
    """
    span = max(
        max(p[0] for p in pts) - min(p[0] for p in pts),
        max(p[1] for p in pts) - min(p[1] for p in pts),
    )
    return max(span, 1e-9) ** 2 * 1e-12


# --------------------------------------------------------------------------- ear clipping

def _ear_clip(pts: list[Point]) -> list[Tri] | None:
    """Clip the best-shaped valid ear at each step. ``None`` when no valid ear exists.

    "Best-shaped" rather than "first found" is what stops it fanning: a plain ear clipper
    walking the ring in order produces exactly the needle-spanning-the-whole-face shape this
    module exists to remove.

    Only *reflex* vertices can lie inside a candidate ear, so only those are tested — checking
    every vertex made a collinear boundary vertex (a T-junction where a bevel strip meets a
    flat face, which real bevels produce at every corner) block every ear and abandon the
    polygon. That bug is why an earlier version of this pass reported no improvement at all.
    """
    n = len(pts)
    if n < 3 or n > MAX_EAR_CLIP:
        return None
    eps = _epsilon(pts)
    ring = list(range(n))
    out: list[Tri] = []

    while len(ring) > 3:
        reflex = {
            ring[k]
            for k in range(len(ring))
            if _cross(pts[ring[k - 1]], pts[ring[k]], pts[ring[(k + 1) % len(ring)]]) < -eps
        }
        best: tuple[float, int, Tri] | None = None
        for k in range(len(ring)):
            ia, ib, ic = ring[k - 1], ring[k], ring[(k + 1) % len(ring)]
            a, b, c = pts[ia], pts[ib], pts[ic]
            if _cross(a, b, c) <= eps:
                continue
            if any(
                _cross(a, b, pts[o]) > eps
                and _cross(b, c, pts[o]) > eps
                and _cross(c, a, pts[o]) > eps
                for o in reflex
                if o not in (ia, ib, ic)
            ):
                continue
            score = aspect_ratio(a, b, c)
            if best is None or score < best[0]:
                best = (score, k, (ia, ib, ic))
        if best is None:
            return None
        out.append(best[2])
        ring.pop(best[1])

    out.append((ring[0], ring[1], ring[2]))
    return out


# ------------------------------------------------------------------------ dynamic program

def _diagonals(pts: list[Point], eps: float) -> list[list[bool]]:
    """``ok[i][j]`` — whether the segment i-j lies inside the polygon and crosses no edge."""
    n = len(pts)
    ok = [[False] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j - i == 1 or (i == 0 and j == n - 1):
                ok[i][j] = ok[j][i] = True
                continue
            ok[i][j] = ok[j][i] = _in_cone(pts, i, j, eps) and _in_cone(pts, j, i, eps) and (
                not _crosses_boundary(pts, i, j, eps)
            )
    return ok


def _in_cone(pts: list[Point], i: int, j: int, eps: float) -> bool:
    n = len(pts)
    a, prev, nxt = pts[i], pts[(i - 1) % n], pts[(i + 1) % n]
    b = pts[j]
    if _cross(prev, a, nxt) >= -eps:  # convex (or straight) corner
        return _cross(a, b, prev) > eps and _cross(b, a, nxt) > eps
    return not (_cross(a, b, nxt) >= -eps and _cross(b, a, prev) >= -eps)


def _crosses_boundary(pts: list[Point], i: int, j: int, eps: float) -> bool:
    n = len(pts)
    a, b = pts[i], pts[j]
    for k in range(n):
        k2 = (k + 1) % n
        if k in (i, j) or k2 in (i, j):
            continue
        c, d = pts[k], pts[k2]
        d1, d2 = _cross(c, d, a), _cross(c, d, b)
        d3, d4 = _cross(a, b, c), _cross(a, b, d)
        if min(abs(d1), abs(d2), abs(d3), abs(d4)) <= eps:
            continue
        if (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0):
            return True
    return False


def _dynamic_program(pts: list[Point]) -> list[Tri] | None:
    """The triangulation minimising the summed aspect ratio, over valid diagonals only.

    Optimal where it applies, which the greedy clipper is not — but it declines more often
    (a rejected diagonal can leave a sub-polygon with no legal split at all), which is why
    the caller keeps both.
    """
    n = len(pts)
    if n < 3 or n > MAX_DP:
        return None
    eps = _epsilon(pts)
    ok = _diagonals(pts, eps)

    cost = [[math.inf] * n for _ in range(n)]
    split = [[-1] * n for _ in range(n)]
    for i in range(n - 1):
        cost[i][i + 1] = 0.0

    for span in range(2, n):
        for i in range(n - span):
            j = i + span
            if not ok[i][j]:
                continue
            for k in range(i + 1, j):
                if not (ok[i][k] and ok[k][j]):
                    continue
                if cost[i][k] == math.inf or cost[k][j] == math.inf:
                    continue
                if _cross(pts[i], pts[k], pts[j]) <= eps:
                    continue
                total = cost[i][k] + cost[k][j] + aspect_ratio(pts[i], pts[k], pts[j])
                if total < cost[i][j]:
                    cost[i][j], split[i][j] = total, k

    if cost[0][n - 1] == math.inf:
        return None

    out: list[Tri] = []
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        k = split[i][j]
        if k < 0:
            continue
        out.append((i, k, j))
        stack.append((i, k))
        stack.append((k, j))
    return out if len(out) == n - 2 else None


# ------------------------------------------------------------------------------- flipping

def _flip(pts: list[Point], tris: list[Tri], rounds: int = 8) -> list[Tri]:
    """Rotate shared edges while it lowers the worse of the two triangles they join.

    Cheap local repair for whatever the two constructive passes leave behind. Edges are
    visited in sorted order and a flip must beat the current pair by a clear margin, so the
    outcome cannot depend on iteration order and cannot oscillate.
    """
    tris = list(tris)
    for _ in range(rounds):
        shared: dict[tuple[int, int], list[int]] = {}
        for idx, (i, j, k) in enumerate(tris):
            for a, b in ((i, j), (j, k), (k, i)):
                shared.setdefault((a, b) if a < b else (b, a), []).append(idx)
        changed = False
        for key in sorted(shared):
            owners = shared[key]
            if len(owners) != 2:
                continue
            first, second = owners
            a, b = key
            c = next((x for x in tris[first] if x not in key), None)
            d = next((x for x in tris[second] if x not in key), None)
            if c is None or d is None or c == d:
                continue
            A, B, C, D = pts[a], pts[b], pts[c], pts[d]
            # The quad A-C-B-D must be strictly convex or the flipped pair overlaps.
            if _cross(C, A, D) * _cross(C, B, D) >= 0 or _cross(A, C, B) * _cross(A, D, B) >= 0:
                continue
            before = max(aspect_ratio(A, B, C), aspect_ratio(A, B, D))
            after = max(aspect_ratio(C, D, A), aspect_ratio(C, D, B))
            if after < before * 0.999:
                tris[first], tris[second] = (a, c, d), (b, d, c)
                changed = True
        if not changed:
            break
    return tris


# --------------------------------------------------------------------------------- public

def best_triangulation(pts: list[Point], current: list[Tri]) -> list[Tri] | None:
    """The lowest-scoring triangulation of ``pts`` found, or ``None`` to keep ``current``.

    ``current`` is a genuine candidate, not just a baseline: on real bevel output it wins on
    roughly two thirds of regions, and a pass that "improved" those would be making the mesh
    worse under the name of a quality step.
    """
    if len(pts) < 3 or len(pts) > MAX_EAR_CLIP:
        return None

    candidates: list[list[Tri]] = []
    for build in (_ear_clip, _dynamic_program):
        produced = build(pts)
        if not produced or len(produced) != len(pts) - 2:
            continue
        candidates.append(produced)
        flipped = _flip(pts, produced)
        if flipped != produced:
            candidates.append(flipped)

    if not candidates:
        return None
    best = min(candidates, key=lambda c: _score(pts, c))
    return best if _score(pts, best) < _score(pts, current) - 1e-9 else None
