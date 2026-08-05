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

from typing import Protocol, Sequence, runtime_checkable

from .geometry import AABB, MeshSnapshot, Transform, Vec3

__all__ = [
    "MeshOps",
    "ModifierOps",
    "MaterialOps",
    "UVBakeOps",
    "ExportOps",
    "RawOps",
    "EngineProtocol",
    "EngineError",
    "EngineUnavailable",
]


class EngineError(RuntimeError):
    """A geometry operation failed inside the engine.

    Carries the rule that broke rather than a raw traceback — Gate A 4.2 requires an
    agent be told *which rule broke, by how much, and what to try next*, because agents
    handed opaque errors loop on the same failing call.
    """

    def __init__(self, rule: str, detail: str, suggestion: str = "") -> None:
        super().__init__(f"{rule}: {detail}" + (f" — {suggestion}" if suggestion else ""))
        self.rule = rule
        self.detail = detail
        self.suggestion = suggestion


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
    ) -> list[str]:
        """Instance ``object_id`` along a polyline.

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

    def merge_by_distance(self, object_id: str, distance: float) -> int:
        """Returns the number of vertices removed."""
        ...

    def fill_holes(self, object_id: str, max_sides: int = 0) -> int:
        """Returns the number of holes filled. ``max_sides=0`` means no limit."""
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
class ExportOps(Protocol):
    def export_gltf(
        self,
        object_ids: Sequence[str],
        path: str,
        *,
        y_up: bool,
        apply_modifiers: bool = True,
    ) -> str:
        """Write glTF/GLB via Blender's own exporter and return the path.

        Deliberately delegated rather than reimplemented: Blender's exporter handles PBR
        and material edge cases correctly. Axis, handedness, unit and budget conversion
        stay in ``src/export/`` as pure functions over plain data so they can be
        round-trip tested without Blender.
        """
        ...


@runtime_checkable
class RawOps(Protocol):
    def execute(self, source: str, namespace: dict | None = None) -> dict:
        """Run arbitrary Python against the live engine context (ADR-009).

        This is unrestricted by explicit user decision. It provides no security boundary,
        it breaks the parametric chain, and it acts as an undo barrier. Callers record
        every invocation as an opaque operation.
        """
        ...


@runtime_checkable
class EngineProtocol(MeshOps, ModifierOps, MaterialOps, UVBakeOps, ExportOps, RawOps, Protocol):
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
