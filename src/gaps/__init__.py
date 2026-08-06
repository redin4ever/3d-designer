"""``gaps`` — the corrective half of ``measure``.

Nine defect classes, nine different repairs (``contracts.DefectClass`` docstrings are
explicit that lumping them into one "fix the gaps" step is the most common mistake in this
domain). ``measure`` detects; this module corrects, and re-runs ``measure``'s own
detectors to confirm a fix actually took rather than trusting a mutating call's own
report. This file is a barrel: re-exports only, no logic.
"""

from .primitives import fill_boundary_holes, merge_shells, weld_duplicates
from .rebuild import fix_normals, remove_loose, split_non_manifold
from .registry import GAPS_SPECS
from .tiered import repair
from .visual_gap import close_visual_gap

__all__ = [
    "fill_boundary_holes",
    "weld_duplicates",
    "remove_loose",
    "fix_normals",
    "split_non_manifold",
    "merge_shells",
    "close_visual_gap",
    "repair",
    "GAPS_SPECS",
]
