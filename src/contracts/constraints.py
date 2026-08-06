"""The declarative constraint vocabulary — how an agent says *where something goes*.

This is the single highest-value design decision in the product, and it has a number
attached. A model producing raw x/y/z coordinates lands within 2x of ground truth about
37% of the time, even when purpose-trained for spatial estimation. A model emitting
declarative constraints resolved by a solver measures 91-95%. Constraints are therefore
the default path and raw coordinates the escape hatch (ADR-004).

Constraints are **stored, not just applied**. That is what lets them re-solve when an
upstream anchor moves — move the stair, and the railing constrained to its outer edge
follows (ADR-002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .geometry import Vec3

__all__ = [
    "ConstraintKind",
    "AnchorKind",
    "Anchor",
    "Constraint",
    "ConstraintSet",
    "Placement",
    "ConstraintError",
    "CYCLE_RULE",
]

CYCLE_RULE = "constraints.cycle"


class ConstraintKind(StrEnum):
    """The twelve constraint types (assumption A-006).

    Sized deliberately: a comparable published system used ten predefined types with a
    DFS solver and measured well. Twelve is the same order of magnitude, biased toward
    the hard-surface and architectural work this product targets.
    """

    ON = "on"
    """Rest on top of a target's upper surface. Vertical placement only."""

    FLUSH_WITH = "flush_with"
    """Share a face plane with the target — no gap, no overlap."""

    CENTRED_ON = "centred_on"
    """Align centres on the named axes."""

    FOLLOWS = "follows"
    """Sweep or array along a target's path/edge. The primitive behind railings, trims,
    fences and pipes. Never per-instance placement, which is what produces uneven
    spacing and instances that miss corners."""

    OFFSET_FROM = "offset_from"
    """A fixed distance from a target, along a named direction."""

    ENDS_AT = "ends_at"
    """Terminate exactly at a target feature — a rail meeting a post centreline rather
    than stopping at an arbitrary parametric interval."""

    PLUMB = "plumb"
    """Parallel to world up, *regardless of the path's slope*. On a stair rake this is
    the difference between vertical posts and posts leaning at the stair angle — the
    single most common naive-generator error."""

    PARALLEL_TO = "parallel_to"
    PERPENDICULAR_TO = "perpendicular_to"
    COPLANAR_WITH = "coplanar_with"

    SPACING = "spacing"
    """Regular interval along a run, with a clear-opening guarantee between neighbours."""

    CLEAR_OF = "clear_of"
    """Maintain at least a stated distance from a target. The declarative form of "do not
    clip"."""


class AnchorKind(StrEnum):
    OBJECT = "object"
    FACE = "face"
    EDGE = "edge"
    VERTEX = "vertex"
    PATH = "path"
    CENTRELINE = "centreline"
    BOUNDS = "bounds"
    WORLD = "world"


@dataclass(frozen=True, slots=True)
class Anchor:
    """What a constraint refers to.

    Anchors are *symbolic*, never resolved coordinates. ``stair_01.outer_edge`` survives
    the stair moving; ``(2.34, 0.0, 1.87)`` does not. This is the whole mechanism behind
    live re-solve.
    """

    kind: AnchorKind
    object_id: str = ""
    feature: str = ""
    index: int | None = None

    @staticmethod
    def world_up() -> "Anchor":
        return Anchor(kind=AnchorKind.WORLD, feature="up")

    def key(self) -> str:
        parts = [self.kind.value, self.object_id, self.feature]
        if self.index is not None:
            parts.append(str(self.index))
        return ":".join(p for p in parts if p)


@dataclass(frozen=True, slots=True)
class Constraint:
    kind: ConstraintKind
    target: Anchor
    value: float | Vec3 | None = None
    axis: Vec3 | None = None
    tolerance: float = 1e-4
    hard: bool = True
    """Hard constraints must be satisfied or the solve fails loudly. Soft constraints are
    satisfied on a best-effort basis and report their residual. Anything expressing
    physical impossibility — ``clear_of``, ``plumb`` — is hard by default."""

    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConstraintSet:
    """Every constraint acting on one object, plus its optional raw-coordinate fallback."""

    object_id: str
    constraints: tuple[Constraint, ...] = ()
    raw_position: Vec3 | None = None
    """The escape hatch (ADR-004). Recorded distinctly from constraints so its use is
    visible in the operation log rather than silent — agents reach for the easy path
    under pressure, and this is how that becomes measurable instead of invisible."""

    def depends_on(self) -> frozenset[str]:
        return frozenset(
            c.target.object_id for c in self.constraints if c.target.object_id
        )

    @property
    def uses_escape_hatch(self) -> bool:
        return self.raw_position is not None and not self.constraints


@dataclass(frozen=True, slots=True)
class Placement:
    """A solved constraint set: concrete position and orientation, plus what it cost."""

    object_id: str
    position: Vec3

    up: Vec3
    """Where the object's own local **+Z** points, expressed in world space.

    Documented here rather than left to each caller's reading, which is the contract
    request `constraints` filed in Phase 4 and adapted around locally. Three modules had
    independently assumed this same meaning — `constraints` in its solver, `align` in
    `make_plumb`, and `ops` in `railing.py`, whose flagship test asserts
    ``rotation.rotate(Vec3(0,0,1)) ≈ Vec3(0,0,1)`` for a plumb post. They agreed by luck;
    now they agree by declaration.

    "Plumb" is exactly ``up == WORLD_UP``.
    """

    forward: Vec3
    """Where the object's own local **+Y** points, in world space. Together with
    :attr:`up` this fixes the orientation completely; the third axis is their cross
    product and is never stored, so the two can never disagree with a stored third."""

    residuals: tuple[tuple[str, float], ...] = ()
    """``(constraint description, unsatisfied amount)`` for soft constraints. Empty when
    every constraint was met exactly."""

    satisfied_all_hard: bool = True


class ConstraintError(ValueError):
    """A constraint set could not be solved.

    Carries the rule that broke and a suggested next step rather than a traceback, per
    Gate A 4.2 — an agent given ``"baluster gap is 112mm, limit is 100mm; reduce spacing
    to 0.09m or add one baluster"`` fixes it in one attempt, where an agent given a
    traceback loops.
    """

    def __init__(self, rule: str, detail: str, suggestion: str = "") -> None:
        super().__init__(f"{rule}: {detail}" + (f" — {suggestion}" if suggestion else ""))
        self.rule = rule
        self.detail = detail
        self.suggestion = suggestion
