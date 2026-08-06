"""``unwrap``: mark seams (agent-supplied or suggested), then unwrap through the engine.

See ``src/uv/README.md``. ``seams=None`` is not "no seams" — it means "decide for me":
:func:`uv.suggest_seams` runs against the object's current snapshot and its result is what
gets marked. Passing an explicit sequence, even an empty one, always wins outright and is
never merged with or filtered against the suggestion — that override is the one the user
asked for by name ("full UV unwrap ... with the agent able to override seams"), and this
function's whole job is making sure it reaches ``EngineProtocol.mark_seams`` unchanged.
"""

from __future__ import annotations

from typing import Sequence

from contracts import EngineProtocol, RuleError

from .quality import compute_uv_proxies
from .results import UVResult
from .seams import suggest_seams

__all__ = ["unwrap", "SeamIndexError"]


class SeamIndexError(ValueError, RuleError):
    """An explicit seam index that does not exist on the mesh.

    Two bases, deliberately, and in that order:

    ``ValueError`` first because ``uv/CLAUDE.md`` recorded this rejection as a plain
    ``ValueError`` on purpose — it is a decision-layer input check, not an engine-reported
    failure — and an existing test pins that. Adding a rule must widen what the failure
    *carries* and never narrow what it *is*.

    ``RuleError`` second because Gate A 4.2, verbatim, is that the agent is told *what rule
    it broke*, and the boundary recognises a named failure by a single ``isinstance`` rather
    than by knowing every module's own exception type. As a bare ``ValueError`` this arrived
    as a raw traceback carrying one long sentence: no rule to match on, and no separable
    next step — while an obviously correct move (ask ``suggest_seams`` for indices) existed
    the whole time.

    ``orchestration.PromotionRefused`` and ``constraints.ConstraintRuleError`` are built the
    same way for the same reason.

    The explicit ``__init__`` is not ceremony. With ``ValueError`` first in the MRO, the
    inherited ``__init__`` is ``ValueError``'s, which takes no keyword arguments — so
    constructing this with ``rule=``/``detail=`` raises ``TypeError`` at the very moment the
    caller is trying to report a different failure. ``ConstraintRuleError`` avoids it only
    because its first base already accepts the same three keywords.
    """

    def __init__(self, rule: str, detail: str, suggestion: str = "") -> None:
        RuleError.__init__(self, rule=rule, detail=detail, suggestion=suggestion)


def unwrap(
    engine: EngineProtocol,
    object_id: str,
    *,
    seams: Sequence[int] | None = None,
    method: str = "angle_based",
    margin: float = 0.001,
) -> UVResult:
    """Unwrap ``object_id``, marking ``seams`` first (or :func:`uv.suggest_seams`'s result
    when ``seams`` is ``None``).

    ``seams=None`` means "decide for me"; an explicit sequence — including an empty one —
    always wins outright and is marked exactly as given, never merged with or filtered
    against the suggestion. This is the one override the user asked for by name, and it must
    reach ``EngineProtocol.mark_seams`` unchanged.

    An explicit ``seams`` sequence containing an index outside
    ``range(len(snapshot.edges()))`` is rejected with ``ValueError`` before it reaches the
    engine — an out-of-range index would otherwise seam the wrong edge silently, exactly the
    failure ``MeshSnapshot.edges()``'s own docstring warns about.
    """
    snapshot = engine.snapshot(object_id)
    edge_count = len(snapshot.edges())

    if seams is None:
        seam_indices: tuple[int, ...] = suggest_seams(snapshot)
    else:
        seam_indices = tuple(seams)
        out_of_range = sorted({i for i in seam_indices if not (0 <= i < edge_count)})
        if out_of_range:
            raise SeamIndexError(
                rule="uv.seam_index_out_of_range",
                detail=(
                    f"unwrap({object_id!r}): seam edge indices {out_of_range} are outside "
                    f"range(0, {edge_count}) of snapshot.edges() — an out-of-range index "
                    "would seam the wrong edge silently"
                ),
                suggestion=(
                    f"{object_id!r} has {edge_count} edges. Call suggest_seams(snapshot) for "
                    "indices that exist, or drop the out-of-range ones"
                ),
            )

    engine.mark_seams(object_id, seam_indices)
    engine.unwrap(object_id, method=method, margin=margin)

    result_snapshot = engine.snapshot(object_id)
    coverage, max_stretch, overlaps = compute_uv_proxies(result_snapshot)
    return UVResult(
        object_id=object_id,
        ok=result_snapshot.uvs is not None,
        seam_count=len(seam_indices),
        coverage=coverage,
        max_stretch=max_stretch,
        overlaps=overlaps,
        detail=f"{method} unwrap, margin={margin:g}, {len(seam_indices)} seam edge(s)",
    )
