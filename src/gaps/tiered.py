"""``repair`` — tiered, re-measured multi-defect correction for one object.

Runs the cheapest, most local repairs first and re-measures with ``measure``'s own
detectors before and after each tier. The returned outcomes are never a sum of what each
underlying primitive claims to have done — they are always derived from a fresh detector
call, so the report is about what is actually left on the mesh, not what was attempted
(see ``CLAUDE.md``).
"""

from __future__ import annotations

from typing import Callable, Sequence

from contracts import DefectClass, Defect, EngineProtocol, RepairOutcome
from measure import (
    find_boundary_holes,
    find_flipped_normals,
    find_loose_or_duplicate,
    find_non_manifold_edges,
    find_non_manifold_vertices,
)

from .primitives import fill_boundary_holes, weld_duplicates
from .rebuild import fix_normals, remove_loose, split_non_manifold

__all__ = ["repair"]

Detector = Callable[[EngineProtocol, str], tuple[Defect, ...]]
Repairer = Callable[[EngineProtocol, str], RepairOutcome]


def _non_manifold(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    return find_non_manifold_edges(engine, object_id) + find_non_manifold_vertices(engine, object_id)


#: Cheapest / most local fixes first. Each entry is (the defect classes it addresses, the
#: repair function, the detector used to measure before/after). ``classes`` filters by
#: membership in the first element.
_TIERS: tuple[tuple[tuple[DefectClass, ...], Repairer, Detector], ...] = (
    ((DefectClass.LOOSE_OR_DUPLICATE,), weld_duplicates, find_loose_or_duplicate),
    ((DefectClass.LOOSE_OR_DUPLICATE,), remove_loose, find_loose_or_duplicate),
    ((DefectClass.BOUNDARY_HOLE,), fill_boundary_holes, find_boundary_holes),
    ((DefectClass.FLIPPED_NORMAL,), fix_normals, find_flipped_normals),
    (
        (DefectClass.NON_MANIFOLD_EDGE, DefectClass.NON_MANIFOLD_VERTEX),
        split_non_manifold,
        _non_manifold,
    ),
)


def repair(
    engine: EngineProtocol, object_id: str, *, classes: Sequence[DefectClass] | None = None
) -> tuple[RepairOutcome, ...]:
    """Run every applicable tier once, re-measuring between each.

    ``classes``, when given, restricts which tiers run to those addressing at least one
    of the named classes; ``None`` runs all of them. A tier whose detector finds nothing
    before running never calls its repair function at all — this is what makes
    :func:`repair` a true no-op on a clean mesh rather than a mutating call that happens
    to change nothing.
    """
    wanted = set(classes) if classes is not None else None
    outcomes: list[RepairOutcome] = []
    for tags, repair_fn, detect in _TIERS:
        if wanted is not None and wanted.isdisjoint(tags):
            continue
        before = detect(engine, object_id)
        if not before:
            outcomes.append(RepairOutcome())
            continue
        repair_fn(engine, object_id)
        after = detect(engine, object_id)
        fixed = max(0, len(before) - len(after))
        reason = f"{len(after)} {tags[0].value} defect(s) remain after repair" if after else ""
        outcomes.append(RepairOutcome(fixed=fixed, skipped=len(after), reason=reason))
    return tuple(outcomes)
