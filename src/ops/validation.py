"""``validate_params`` and ``acceptance_for`` — entry validation and the definition-of-done
half of every operation in this package (ADR-004, ADR-005).

Every operation's parameters are validated on entry and re-measurable on exit. ADR-005's
programmatic definition-of-done depends on both halves existing: a handler that skips
``validate_params`` lets a negative dimension or an impossible spacing reach the engine as
an opaque failure three calls later; an operation with no ``acceptance_for`` query is an
operation nobody — not the agent, not a QA pass — can verify.
"""

from __future__ import annotations

from typing import Any

from contracts import AcceptanceQuery

__all__ = ["validate_params", "acceptance_for"]

_NOT_IMPLEMENTED = "ops.{name}: not implemented"


def validate_params(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """Check ``params`` against ``kind``'s own requirements and return them, unchanged, on
    success.

    Must raise :class:`~contracts.ToolError` — never a bare ``KeyError``, ``ValueError`` or
    ``TypeError`` — naming the offending parameter in ``detail`` and carrying an actionable
    ``suggestion``, for at least:

    - a missing required parameter,
    - a dimension (length, height, thickness, width, depth, a size component) that is zero
      or negative,
    - a count (``treads``, ``count_x``, ``count_y``) that is zero,
    - a spacing (``post_spacing``, ``spacing``) larger than the arc length of the ``path``
      it is measured against — computed from ``path`` itself, never from the engine (this
      function takes no engine argument by design: everything it checks is knowable from
      ``params`` alone).

    Gate A 4.2's bar: "baluster gap 112mm exceeds the 100mm limit, reduce spacing to 0.09"
    fixes the call in one attempt; a traceback does not. Every ``ToolError`` this function
    raises is held to that bar, not just to naming the parameter.

    ``kind`` not present in :data:`ops.OPS` is itself a :class:`~contracts.ToolError`
    naming the unknown kind and listing the known ones — never a silent pass-through.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="validate_params"))


def acceptance_for(kind: str, params: dict[str, Any]) -> tuple[AcceptanceQuery, ...]:
    """The re-runnable definition-of-done for one ``add_*``/``array_along`` call, given the
    params it would be (or was) called with.

    Every kind registered in :data:`ops.OPS` must return **at least one** query here — an
    operation with no acceptance query cannot be checked as done, which defeats ADR-005's
    entire verification split (measurement decides hard facts; the agent decides
    appearance only after the hard facts already pass). Each returned query must be
    individually well-formed per :class:`~contracts.AcceptanceQuery`'s own
    ``__post_init__`` — a query with no comparison and no forbidden defects is not a
    definition of done, it is a query that cannot fail.

    Indicative, non-exhaustive, per kind: ``add_railing`` returns at least one query
    forbidding ``DefectClass.PART_CLIPPING`` between balusters and one checking the top
    rail's extent against ``height``; ``add_staircase`` checks total rise; ``add_opening``
    forbids ``DefectClass.VISUAL_GAP`` at the cut and checks that a triangle-count or
    volume metric on the wall actually changed; ``add_lod_chain`` checks each level's
    ``TRIANGLE_COUNT`` is strictly less than the one before.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED.format(name="acceptance_for"))
