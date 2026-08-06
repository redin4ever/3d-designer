"""Pure boundary-loop grouping for ``fill_holes`` — no bpy.

Deliberately independent of ``testing.mesh_helpers.boundary_loops`` (same algorithm, same
reason as ``_curve.py``): production code in ``src/engine/`` must not depend on
``src/testing/`` — see ``src/engine/CLAUDE.md``'s boundary rules.
"""

from __future__ import annotations

from typing import Sequence

__all__ = ["boundary_loops"]


def boundary_loops(edges: Sequence[tuple[int, int]]) -> list[list[int]]:
    """Group boundary edges (each bounding exactly one face) into closed vertex loops.

    Each loop is one hole. The starting direction of a loop is arbitrary — it only flips
    the winding of the face later built from it, not the topology — so any traversal that
    stays on unvisited boundary edges produces a usable result.
    """
    adjacency: dict[int, list[int]] = {}
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    unvisited = set(edges)
    loops: list[list[int]] = []
    while unvisited:
        a, b = next(iter(unvisited))
        unvisited.discard((a, b))
        loop = [a, b]
        while True:
            nxt = None
            for cand in adjacency.get(loop[-1], []):
                e = (min(loop[-1], cand), max(loop[-1], cand))
                if e in unvisited:
                    nxt = cand
                    unvisited.discard(e)
                    break
            if nxt is None or nxt == loop[0]:
                break
            loop.append(nxt)
        if len(loop) >= 3:
            loops.append(loop)
    return loops
