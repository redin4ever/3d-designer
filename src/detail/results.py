"""``DetailResult`` — the shared outcome type every detail pass in this module returns.

Real, constructed data — not a stub. A frozen dataclass has no body to implement, and every
function in ``edges.py``, ``apply.py``, ``surface.py`` and ``materials.py`` needs this exact
shape to exist at import time so their throwing stubs can still declare a correct return
type.

Why a bare ``bool`` return is not enough: ``contracts.RepairOutcome`` already made this
argument once (see its own docstring) — a caller cannot tell "nothing needed doing" apart
from "changed nothing and something is wrong" from a boolean alone. ``changed=False`` here
must mean the same thing every time: this pass looked, found nothing that qualified, and
correctly did nothing. Reporting a no-op as ``changed=True`` is the specific failure Gate A
8.3 exists to prevent — a pass that always claims success trains the calling agent to stop
checking.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DetailResult"]


@dataclass(frozen=True, slots=True)
class DetailResult:
    """What one detail pass did to one object (or material).

    ``object_id`` names the mesh object the pass touched, except for
    :func:`detail.vary_roughness`, which is material-scoped and puts the ``material_id``
    here instead — there is one result shape across every pass in this module rather than a
    second, near-identical type for the one material-only function.

    ``triangles_before``/``triangles_after`` are always populated, even for a pass that
    never touches geometry (:func:`detail.vary_roughness`, :func:`detail.clamp_albedo` is
    not in this shape at all — it returns a plain tuple, not a ``DetailResult``, because it
    computes a colour with no object involved). For a material-only pass the two counts are
    equal by construction; that equality is itself the signal that no mesh was touched, so a
    caller does not need a second field to learn it.
    """

    object_id: str
    changed: bool
    triangles_before: int
    triangles_after: int
    detail: str = ""
