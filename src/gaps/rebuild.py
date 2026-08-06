"""Repairs that rebuild an object's geometry from its snapshot via ``create_mesh``.

None of these has a matching ``EngineProtocol`` primitive: there is no "delete this loose
vertex", "flip this one face", or "duplicate this pinch vertex" method, because the real
engine exposes no such single operation and ``src/contracts/`` cannot be edited to add one
(it is a frozen surface owned elsewhere — see ``README.md``). Every function here instead
reads ``engine.snapshot``, computes the corrected vertex/triangle arrays in plain Python —
the same kind of pure computation ``measure`` already does over a snapshot — and hands the
result back through ``engine.delete`` + ``engine.create_mesh``, the one primitive general
enough to realise an arbitrary geometry change. This is composition of engine primitives,
not a second mesh-editing backend.
"""

from __future__ import annotations

import re
from typing import Sequence

from contracts import Defect, EngineProtocol, RepairOutcome, Vec3
from measure import find_flipped_normals, find_non_manifold_edges, find_non_manifold_vertices

__all__ = ["remove_loose", "fix_normals", "split_non_manifold"]

_TRIANGLE_LIST = re.compile(r"triangle\(s\) \[([0-9, ]*)\]")


def _rebuild(
    engine: EngineProtocol,
    object_id: str,
    vertices: Sequence[Vec3],
    triangles: Sequence[tuple[int, int, int]],
) -> None:
    """Replace ``object_id``'s geometry, keeping its id and transform.

    ``create_mesh`` on a live id would silently mint ``object_id.001`` instead of
    overwriting it (``FakeEngine._unique``) — deleting first is what keeps the id stable,
    which every caller in this file needs.
    """
    transform = engine.snapshot(object_id).transform
    engine.delete(object_id)
    engine.create_mesh(object_id, list(vertices), list(triangles), transform=transform)


def remove_loose(engine: EngineProtocol, object_id: str) -> RepairOutcome:
    """Drop every vertex referenced by no triangle.

    ``DefectClass.LOOSE_OR_DUPLICATE`` — the *loose* half; see
    :func:`gaps.weld_duplicates` for the duplicate half. Rebuilding necessarily flattens
    any n-gon face to its triangulation — ``MeshSnapshot`` does not carry original polygon
    structure to rebuild with (``CLAUDE.md``).
    """
    snap = engine.snapshot(object_id)
    referenced = {v for tri in snap.triangles for v in tri}
    loose_count = len(snap.vertices) - len(referenced)
    if loose_count == 0:
        return RepairOutcome()  # nothing unreferenced — do not touch the mesh at all

    keep = sorted(referenced)
    remap = {old: new for new, old in enumerate(keep)}
    vertices = [snap.vertices[i] for i in keep]
    triangles = [tuple(remap[i] for i in tri) for tri in snap.triangles]
    _rebuild(engine, object_id, vertices, triangles)

    after = engine.snapshot(object_id)
    remaining = len(after.vertices) - len({v for tri in after.triangles for v in tri})
    fixed = loose_count - remaining
    return RepairOutcome(
        fixed=fixed,
        skipped=remaining,
        reason=f"{remaining} vertex/vertices still referenced by no face" if remaining else "",
    )


def _flagged_triangles(defects: tuple[Defect, ...]) -> set[int]:
    """Recover which triangle indices ``measure.find_flipped_normals`` flagged.

    ``Defect`` carries no structured index field (``contracts`` is frozen — see
    ``README.md``); its ``detail`` string is the only place the indices survive, in the
    exact format ``topology.py`` writes them. Fragile by construction, and the reason this
    lives beside a comment rather than silently — if that string ever changes shape, this
    returns an empty set and the caller reports the defect as unfixed rather than guessing.
    """
    found: set[int] = set()
    for d in defects:
        m = _TRIANGLE_LIST.search(d.detail)
        if not m:
            continue
        found.update(int(tok) for tok in m.group(1).split(",") if tok.strip())
    return found


def fix_normals(engine: EngineProtocol, object_id: str) -> RepairOutcome:
    """Reverse the winding of exactly the triangles ``measure`` flags as flipped.

    ``DefectClass.FLIPPED_NORMAL``. Deliberately not
    ``engine.recalculate_normals(object_id)``: that primitive only ever flips *every* face
    (``inside=True``) or none (``inside=False``), and reversing every face leaves the
    relative winding disagreement between neighbours — which is what the detector actually
    checks — completely unchanged. Only a targeted, per-triangle fix changes the answer.
    """
    before = find_flipped_normals(engine, object_id)
    if not before:
        return RepairOutcome()

    flagged = _flagged_triangles(before)
    if not flagged:
        return RepairOutcome(
            fixed=0,
            skipped=len(before),
            reason="could not recover which triangles are flipped from the defect detail",
        )

    snap = engine.snapshot(object_id)
    triangles = [
        tuple(reversed(t)) if i in flagged else t for i, t in enumerate(snap.triangles)
    ]
    _rebuild(engine, object_id, snap.vertices, triangles)

    after = find_flipped_normals(engine, object_id)
    fixed = max(0, len(before) - len(after))
    return RepairOutcome(
        fixed=fixed, skipped=len(after), reason=f"{len(after)} flipped normal(s) remain" if after else "",
    )


def split_non_manifold(engine: EngineProtocol, object_id: str) -> RepairOutcome:
    """Report non-manifold edges/vertices — this package cannot fix them yet.

    ``DefectClass.NON_MANIFOLD_EDGE`` and ``NON_MANIFOLD_VERTEX``. Both docstrings
    prescribe real mesh surgery (split the fan; duplicate the vertex, one copy per fan)
    that ``EngineProtocol`` has no primitive for. A hand-rolled duplicate-the-vertex fix
    was prototyped and rejected: the two coincident copies it produces are immediately
    re-flagged by ``measure.find_loose_or_duplicate``, trading one defect for another
    rather than actually resolving it (see ``CLAUDE.md``). Reporting the true count here,
    rather than a false ``fixed``, is what keeps a caller from believing a mesh is clean
    when it is not.
    """
    defects = find_non_manifold_edges(engine, object_id) + find_non_manifold_vertices(
        engine, object_id
    )
    if not defects:
        return RepairOutcome()
    return RepairOutcome(
        fixed=0,
        skipped=len(defects),
        reason=(
            f"{len(defects)} non-manifold edge/vertex defect(s) need mesh surgery this "
            "package has no engine primitive for — not attempted"
        ),
    )
