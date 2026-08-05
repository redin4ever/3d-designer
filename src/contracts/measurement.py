"""Measurement and defect vocabulary — the shape of "what is true about this geometry".

ADR-005 splits verification authority: measurement decides hard facts (manifold,
clipping, scale, transforms, budget, constraint satisfaction), the agent decides
appearance. These types are the measurement half of that split, and they are what makes
a definition-of-done a *re-run query* rather than an agent's claim — agents self-report
false success in 13-89% of failures and LLM judges catch it at barely above chance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .geometry import Vec3

__all__ = [
    "MetricKind",
    "DefectClass",
    "Severity",
    "Measurement",
    "Defect",
    "MeasurementReport",
    "AcceptanceQuery",
    "AcceptanceResult",
]


class MetricKind(StrEnum):
    """The seven metric queries. Every one of these is a number the tool computes and
    hands over, never a judgement the model makes from a render — models land within 2x
    of ground truth on visual distance estimation about 37% of the time."""

    BOUNDS = "bounds"
    DIMENSIONS = "dimensions"
    DISTANCE = "distance"
    ANGLE = "angle"
    GAP_WIDTH = "gap_width"
    VOLUME = "volume"
    TRIANGLE_COUNT = "triangle_count"


class DefectClass(StrEnum):
    """The nine defect classes.

    These are genuinely different problems with different detection and different repair.
    Treating them as one "fix the gaps" step is the most common mistake in this domain.
    Note the last two are not mesh-validity defects at all — a part can be a perfect
    manifold and still be in the wrong place relative to another part.
    """

    BOUNDARY_HOLE = "boundary_hole"
    """A closed loop of edges each bounding exactly one face. Repair: triangulate the loop."""

    NON_MANIFOLD_EDGE = "non_manifold_edge"
    """An edge with three or more incident faces. Repair: split the fan."""

    NON_MANIFOLD_VERTEX = "non_manifold_vertex"
    """A vertex whose incident faces form more than one fan — two cones touching at a
    point. Repair: duplicate the vertex, one copy per fan."""

    LOOSE_OR_DUPLICATE = "loose_or_duplicate"
    """Vertices/edges with no attached face, or coincident vertices not welded."""

    FLIPPED_NORMAL = "flipped_normal"
    """Face winding inconsistent with its neighbours. Invisible in solid shading with
    backface culling off, and it breaks booleans and exports."""

    SELF_INTERSECTION = "self_intersection"
    """Two non-adjacent triangles of the same mesh sharing points in 3D."""

    UNAPPLIED_TRANSFORM = "unapplied_transform"
    """Non-unit object scale not baked into mesh data. Looks correct in the viewport and
    silently corrupts bevel width, boolean results and physics."""

    PART_CLIPPING = "part_clipping"
    """Two *different* objects interpenetrating where they should not.

    This is not a mesh-validity defect — both parts can be individually perfect. It is
    also the one defect no library can classify on geometry alone: a post socketed 50mm
    into a deck and two posts overlapping by 50mm are identical BVH overlaps. The
    difference is intent, which must be declared (see :class:`JoineryIntent`), never
    inferred.
    """

    VISUAL_GAP = "visual_gap"
    """Two parts that should meet and do not — a tread short of its stringer. Passes
    every manifold and watertight check, because each part is individually fine."""


class Severity(StrEnum):
    BLOCKER = "blocker"
    """Will fail on import into an engine or a slicer."""

    WARNING = "warning"
    """Wrong, but survivable. The default for anything the user chose not to gate on."""

    INFO = "info"
    """Worth knowing. Never acted on automatically."""


@dataclass(frozen=True, slots=True)
class Measurement:
    """One computed number, with its units, handed to the agent as fact."""

    kind: MetricKind
    value: float | tuple[float, float, float]
    unit: str
    subject: str
    """Object id, or ``"a|b"`` for a pairwise measurement."""
    detail: str = ""

    def describe(self) -> str:
        if isinstance(self.value, tuple):
            v = " x ".join(f"{c:.4g}" for c in self.value)
        else:
            v = f"{self.value:.4g}"
        return f"{self.subject} {self.kind}: {v}{self.unit}"


@dataclass(frozen=True, slots=True)
class Defect:
    """One reproducible problem, located and quantified.

    ``magnitude`` is what makes a defect actionable rather than an alarm — Gate A 4.2
    requires an agent be told which rule broke *and by how much*.
    """

    defect_class: DefectClass
    severity: Severity
    object_id: str
    detail: str
    magnitude: float = 0.0
    unit: str = "m"
    location: Vec3 | None = None
    other_object_id: str | None = None
    suggestion: str = ""

    def describe(self) -> str:
        where = f"{self.object_id}"
        if self.other_object_id:
            where += f" ∩ {self.other_object_id}"
        mag = f", {self.magnitude:.4g}{self.unit}" if self.magnitude else ""
        tail = f" — {self.suggestion}" if self.suggestion else ""
        return f"[{self.severity}] {self.defect_class} at {where}{mag}: {self.detail}{tail}"


@dataclass(frozen=True, slots=True)
class MeasurementReport:
    """Everything measurement knows about a scope, at one moment."""

    measurements: tuple[Measurement, ...] = ()
    defects: tuple[Defect, ...] = ()
    scope: tuple[str, ...] = ()
    """Object ids actually examined. At thousands of objects, checks are scoped to
    changed objects plus their spatial neighbours (ADR-011); this field records what was
    genuinely looked at so a clean report cannot be mistaken for a whole-scene clean
    bill of health."""
    full_scene: bool = False

    @property
    def blockers(self) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.severity is Severity.BLOCKER)

    @property
    def is_clean(self) -> bool:
        return not self.defects

    def of_class(self, cls: DefectClass) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.defect_class is cls)


@dataclass(frozen=True, slots=True)
class AcceptanceQuery:
    """A machine-checkable definition of done.

    Every operation and every phase promotion carries one. It is re-run against live
    geometry to decide completion — never an agent's statement that it finished, and
    never a second agent's opinion of that statement. Both are measured unreliable in
    exactly the direction that matters: false positives.
    """

    query_id: str
    description: str
    metric: MetricKind | None = None
    forbidden_defects: tuple[DefectClass, ...] = ()
    subject: str = ""
    expected: float | None = None
    tolerance: float = 1e-4
    comparison: str = "eq"
    """eq | lte | gte | none — ``none`` means the query is purely about absent defects."""

    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    query_id: str
    passed: bool
    actual: float | None = None
    reason: str = ""
    defects: tuple[Defect, ...] = ()
