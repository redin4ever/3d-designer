"""``EngineProtocol`` — the sole typed boundary between bpy and everything else.

This is the most load-bearing file in the repository. ``src/engine/`` is the only module
permitted to ``import bpy``; every other module is written against these Protocols and is
handed a concrete or fake implementation at the composition root (ADR-008).

Two consequences follow, and both are the reason this file exists:

1. Every module except ``engine`` runs its full test suite against ``FakeEngine`` with no
   Blender installed.
2. A Blender version bump — and Blender ships breaking Python API changes with no
   deprecation policy (ADR-001) — touches ``src/engine/`` internals and nothing else.

Methods here are **generic primitives**, deliberately. Domain vocabulary ("railing",
"staircase") lives in ``src/ops/``. If a method name here mentions a building element,
the seam has been crossed in the wrong direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from .errors import RuleError
from .geometry import AABB, MeshSnapshot, Transform, Vec3

__all__ = [
    "RepairOutcome",
    "ModelImportResult",
    "SUPPORTED_MODEL_EXTENSIONS",
    "MeshOps",
    "ModifierOps",
    "MaterialOps",
    "UVBakeOps",
    "ImportOps",
    "ExportOps",
    "RawOps",
    "EngineProtocol",
    "EngineError",
    "EngineUnavailable",
]


SUPPORTED_MODEL_EXTENSIONS: tuple[str, ...] = (
    ".glb", ".gltf", ".fbx", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc",
)
"""Interchange formats supported by the installed Blender 5.2 adapter.

``.blend`` is deliberately absent: a forge3d project is a versioned ``.forge3d`` package,
while opening an arbitrary Blender working file would replace process-level scene state.
"""


class EngineError(RuleError):
    """A geometry operation failed inside the engine.

    Carries the rule that broke rather than a raw traceback — Gate A 4.2 requires an
    agent be told *which rule broke, by how much, and what to try next*, because agents
    handed opaque errors loop on the same failing call.

    Derives from :class:`~contracts.errors.RuleError` so that "did this failure name a
    rule" is one ``isinstance`` check at the boundary rather than four duck-typed ones.
    ``RuleError`` is itself a ``RuntimeError``, so nothing that already caught this
    changes meaning.
    """


class EngineUnavailable(EngineError):
    """The requested capability needs a real Blender window/context that the in-process
    ``bpy`` module does not have, and the subprocess fallback is not available.

    ``bpy``-as-a-module has no ``bpy.context.window`` at all — a stricter subset than
    ``blender --background``. UV bake is the operation most likely to hit this.
    """

    def __init__(self, capability: str) -> None:
        super().__init__(
            rule="engine.capability_unavailable",
            detail=f"{capability} needs a windowed Blender context",
            suggestion="install Blender and enable the subprocess fallback, or skip this step",
        )
        self.capability = capability


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    """The result of a repair operation.

    A bare integer cannot distinguish "nothing needed doing" from "found work and could
    not do it" — both return zero. A caller building a report from that says *0 holes
    remain* about a mesh that still has an unfilled one.
    """

    fixed: int = 0
    skipped: int = 0
    reason: str = ""

    @property
    def complete(self) -> bool:
        return self.skipped == 0


@dataclass(frozen=True, slots=True)
class ModelImportResult:
    """Meshes created by one atomic import and any non-fatal omissions."""

    object_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.object_ids:
            raise ValueError("a successful model import must create at least one mesh")
        if len(set(self.object_ids)) != len(self.object_ids):
            raise ValueError("a model import cannot report the same object twice")


@runtime_checkable
class MeshOps(Protocol):
    """Create and edit mesh data."""

    def create_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
        transform: Transform | None = None,
    ) -> str: ...

    def create_primitive(
        self, object_id: str, kind: str, size: Vec3, transform: Transform | None = None
    ) -> str:
        """``kind`` is one of: cube, cylinder, sphere, plane, cone, torus."""
        ...

    def replace_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
    ) -> None:
        """Swap an existing object's mesh data, keeping everything that is not geometry.

        The object's transform, material slots, per-face material indices and UV layers
        survive. Only vertices and faces change.

        Without this, the only way to rewrite an object's triangles is ``delete`` then
        ``create_mesh`` under the same id — which loses all four of those. That is a real
        limit, not a theoretical one: ``detail.cleanup_bevel_topology`` has to *decline* on
        any object that has been UV unwrapped or carries more than one material slot,
        because rebuilding it would silently throw the unwrap away. Filed as a contract
        request by the module that hit it, rather than worked around by losing data.

        Implementations must reject a vertex/face set that does not describe a mesh at all,
        the same way ``create_mesh`` does — a caller handing over an empty list has a bug,
        and emptying the object is the least useful possible interpretation of it.
        """
        ...

    def duplicate(self, object_id: str, new_id: str, transform: Transform | None = None) -> str: ...

    def delete(self, object_id: str) -> None: ...

    def set_transform(self, object_id: str, transform: Transform) -> None: ...

    def apply_transform(self, object_id: str, *, location: bool, rotation: bool, scale: bool) -> None:
        """Bake object-level transform into mesh data.

        Unapplied non-uniform scale silently corrupts bevel width, boolean results and
        physics while looking correct in a viewport. Callers apply scale before any of
        those operations, not after discovering the corruption.
        """
        ...

    def join(self, target_id: str, source_ids: Sequence[str]) -> str: ...

    def separate_loose(self, object_id: str) -> list[str]: ...

    def snapshot(self, object_id: str) -> MeshSnapshot: ...

    def list_objects(self) -> list[str]: ...

    def exists(self, object_id: str) -> bool: ...

    def world_bounds(self, object_id: str) -> AABB: ...


@runtime_checkable
class ModifierOps(Protocol):
    """Modifier-stack operations. Every one is applied destructively and immediately —
    the parametric history lives in the scene document (ADR-002), not in Blender's stack,
    so that replay is deterministic and does not depend on Blender's evaluation order."""

    def bevel_edges(
        self,
        object_id: str,
        width: float,
        segments: int = 2,
        edge_indices: Sequence[int] | None = None,
    ) -> None:
        """``edge_indices`` of None means every edge. Callers should pass an explicit
        selection — the heuristic that chooses which edges plausibly catch light lives
        in ``src/detail/``, and blanket beveling is itself an artificiality tell."""
        ...

    def boolean(self, target_id: str, cutter_id: str, mode: str, solver: str = "exact") -> None:
        """``mode``: union | difference | intersect. ``solver``: fast | exact | manifold.

        None of the three solvers is unconditionally correct. ``fast`` breaks on coplanar
        and non-manifold input; ``exact`` has a documented nearly-coplanar bug;
        ``manifold`` guarantees manifold output but rejects non-manifold input. Callers
        pre-check manifoldness and choose accordingly — never default to ``fast`` for
        anything that will be exported.
        """
        ...

    def solidify(self, object_id: str, thickness: float) -> None: ...

    def array_along_curve(
        self,
        object_id: str,
        curve_points: Sequence[Vec3],
        spacing: float,
        *,
        keep_upright: bool,
        extra_points: Sequence[Vec3] = (),
        name_template: str = "{base}_i{index:03d}",
    ) -> list[str]:
        """Instance ``object_id`` along a polyline.

        ``name_template`` lets the caller predict every instance's id before the call, so
        an operation can pre-declare a ``ConstraintSet`` per instance and have live
        re-solve reach individual balusters rather than only the array as a whole.
        Available fields: ``base``, ``index``.

        ``keep_upright=True`` keeps each instance's own +Z parallel to world up rather
        than to the path normal. On a sloped path — a stair rake — the difference is
        between plumb posts and posts leaning at the stair angle, which is the single
        most common naive-generator error.

        ``extra_points`` are forced instance positions in addition to the regular pitch;
        direction changes must appear here or a corner gets either a gap or a doubled
        instance.
        """
        ...

    def decimate(self, object_id: str, ratio: float) -> None: ...

    def recalculate_normals(self, object_id: str, *, inside: bool = False) -> None: ...

    def merge_by_distance(self, object_id: str, distance: float) -> "RepairOutcome":
        """Weld coincident vertices."""
        ...

    def fill_holes(self, object_id: str, max_sides: int = 0) -> "RepairOutcome":
        """Triangulate boundary loops. ``max_sides=0`` means no limit."""
        ...


@runtime_checkable
class MaterialOps(Protocol):
    def create_material(self, name: str, base_color: tuple[float, float, float]) -> str: ...

    def set_pbr(
        self,
        material_id: str,
        *,
        base_color: tuple[float, float, float] | None = None,
        roughness: float | None = None,
        metallic: float | None = None,
    ) -> None:
        """Real materials never reflect 0% or 100% of light. Non-metal albedo sits around
        sRGB 60-240 and metal around 180-250; uniform roughness across a surface is the
        loudest 'this is CG' signal there is. Enforcement of those ranges is a
        ``src/detail/`` decision, not an engine one."""
        ...

    def assign_material(self, object_id: str, material_id: str, slot: int = 0) -> None: ...

    def create_texture_material(self, material: object) -> str: ...

    def assign_texture_material(
        self, object_id: str, material_id: str, slot: int = 0, material: object | None = None
    ) -> None: ...


@runtime_checkable
class UVBakeOps(Protocol):
    def unwrap(self, object_id: str, *, method: str = "angle_based", margin: float = 0.001) -> None: ...

    def mark_seams(self, object_id: str, edge_indices: Sequence[int]) -> None: ...

    def bake(
        self, object_id: str, channels: Sequence[str], resolution: int, output_dir: str
    ) -> dict[str, str]:
        """Returns ``{channel: filepath}``.

        May raise :class:`EngineUnavailable` — baking generally needs a windowed context
        that in-process ``bpy`` does not have. This is the operation most likely to fall
        back to a Blender subprocess.
        """
        ...


@runtime_checkable
class ImportOps(Protocol):
    def import_model(
        self,
        path: str,
        *,
        source_up: str = "AUTO",
        unit_scale: float = 1.0,
        flatten: bool = True,
    ) -> ModelImportResult:
        """Import one supported model atomically.

        Implementations keep mesh geometry and materials, deterministically rename incoming
        collisions, and report ignored non-mesh content through ``warnings``. ``source_up``
        is ``AUTO``, ``X``, ``Y`` or ``Z``; the result is always internal metres and Z-up.
        """
        ...


@runtime_checkable
class ExportOps(Protocol):
    def export_model(
        self,
        object_ids: Sequence[str],
        path: str,
        *,
        y_up: bool,
        mirror_x: bool = False,
        negate_rotation: bool = False,
        scale: float = 1.0,
        apply_modifiers: bool = True,
    ) -> str:
        """Write a supported interchange format inferred from ``path`` and return it."""
        ...

    def export_gltf(
        self,
        object_ids: Sequence[str],
        path: str,
        *,
        y_up: bool,
        mirror_x: bool = False,
        negate_rotation: bool = False,
        scale: float = 1.0,
        apply_modifiers: bool = True,
    ) -> str:
        """Write glTF/GLB via Blender's own exporter and return the path.

        Deliberately delegated rather than reimplemented: Blender's exporter handles PBR
        and material edge cases correctly. The *decision* about which conversion applies
        stays in ``src/export/`` as pure functions over the profile table, so it is
        round-trip testable without Blender; this method just carries the answer through.

        Every field of the conversion has a parameter here on purpose. An earlier draft
        exposed only ``y_up``, which left ``mirror_x`` and ``negate_rotation`` — the two a
        left-handed target needs together — with no way to reach the exporter. The only
        remaining route would have been mutating live object transforms before the call
        and reverting after: destructive, lock-requiring, and exactly the silent
        round-trip mirroring bug the profile table exists to prevent.
        """
        ...


@runtime_checkable
class RawOps(Protocol):
    def execute(self, source: str, namespace: dict | None = None) -> dict:
        """Run arbitrary Python against the live engine context (ADR-009).

        Unrestricted by explicit user decision. It provides no security boundary, it
        breaks the parametric chain, and it acts as an undo barrier. Callers record every
        invocation as an opaque operation.

        **This is the one method that cannot honour the error contract itself.** Arbitrary
        code raises arbitrary exceptions, so the rest of this file's promise — that an
        agent is told which rule broke, never a raw traceback — has to be kept by the
        caller instead. Every call site must wrap it:

        .. code-block:: python

            try:
                ns = engine.execute(source)
            except Exception as exc:
                raise EngineError(
                    "raw.execution_failed", f"{type(exc).__name__}: {exc}",
                    "the code you supplied raised; the scene may be partly modified"
                ) from exc

        Not wrapping it is how an agent ends up looping on a traceback it cannot act on.
        """
        ...


@runtime_checkable
class EngineProtocol(
    MeshOps, ModifierOps, MaterialOps, UVBakeOps, ImportOps, ExportOps, RawOps, Protocol
):
    """The complete engine surface. ``src/engine/`` implements it against bpy; the test
    fake implements it in pure Python."""

    @property
    def backend_name(self) -> str:
        """e.g. ``"bpy-5.2.0"`` or ``"fake"``. Recorded in the scene document so a
        reader can tell which engine produced a given result."""
        ...

    def reset(self) -> None:
        """Clear all scene data. Replay starts from here (ADR-002)."""
        ...
