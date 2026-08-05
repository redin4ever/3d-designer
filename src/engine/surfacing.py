"""``MaterialOps`` + ``UVBakeOps`` — materials, unwrap, seams and bake against bpy's data API.

Combined per the suggested file split: both are "surfacing" rather than geometry, and bake
is UV-dependent. ``bake`` is the one method this whole module might legitimately never
manage to satisfy on a given machine — see ``bake``'s own docstring for how a genuine
attempt is distinguished from an environment gap.
"""

from __future__ import annotations

from typing import Sequence

from contracts import EngineError, EngineUnavailable

from ._shared import (
    build_snapshot_topology,
    canonical_edges,
    edge_lookup_by_original_vertices,
    get_material,
    get_object,
    write_bmesh,
)

__all__ = ["SurfacingMixin"]

_UNWRAP_METHODS = {"angle_based": "ANGLE_BASED", "conformal": "CONFORMAL", "minimum_stretch": "MINIMUM_STRETCH"}

#: channel name -> (bake type, pass_filter). Only ``albedo`` is exercised by the
#: conformance suite; the rest are a reasonable best-effort mapping onto Cycles' bake passes
#: (there is no native "metallic" pass — Cycles bakes shader outputs, not arbitrary BSDF
#: inputs — so it falls back to the DIFFUSE/COLOR pass like every other unrecognised name).
_BAKE_TYPES = {
    "albedo": ("DIFFUSE", {"COLOR"}),
    "diffuse": ("DIFFUSE", {"COLOR"}),
    "normal": ("NORMAL", None),
    "roughness": ("ROUGHNESS", None),
    "ao": ("AO", None),
    "emission": ("EMIT", None),
}


def _find_principled(node_tree):
    for node in node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def _find_input(node, *names: str):
    """Look up a node's input socket by name, checked at runtime — ADR-001: Principled BSDF
    socket names have changed between Blender versions with no deprecation policy, so this
    is never assumed by fixed index."""
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    lowered = {n.lower() for n in names}
    for socket in node.inputs:
        if socket.name.lower() in lowered:
            return socket
    return None


class SurfacingMixin:
    """``MaterialOps`` + ``UVBakeOps`` surface, mixed into
    :class:`~engine.session.BlenderEngine`."""

    # ---------------------------------------------------------------- materials

    def create_material(self, name: str, base_color: tuple[float, float, float]) -> str:
        import bpy

        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = (*base_color, 1.0)
        bsdf = _find_principled(mat.node_tree)
        if bsdf is not None:
            socket = _find_input(bsdf, "Base Color", "Color")
            if socket is not None:
                socket.default_value = (*base_color, 1.0)
        return mat.name

    def set_pbr(
        self,
        material_id: str,
        *,
        base_color: tuple[float, float, float] | None = None,
        roughness: float | None = None,
        metallic: float | None = None,
    ) -> None:
        mat = get_material(material_id)
        if not mat.use_nodes:
            mat.use_nodes = True
        bsdf = _find_principled(mat.node_tree)

        if base_color is not None:
            mat.diffuse_color = (*base_color, 1.0)
            if bsdf is not None:
                socket = _find_input(bsdf, "Base Color", "Color")
                if socket is not None:
                    socket.default_value = (*base_color, 1.0)
        if roughness is not None and bsdf is not None:
            socket = _find_input(bsdf, "Roughness")
            if socket is not None:
                socket.default_value = roughness
        if metallic is not None and bsdf is not None:
            socket = _find_input(bsdf, "Metallic")
            if socket is not None:
                socket.default_value = metallic

    def assign_material(self, object_id: str, material_id: str, slot: int = 0) -> None:
        obj = get_object(object_id)
        mat = get_material(material_id)
        while len(obj.data.materials) <= slot:
            obj.data.materials.append(None)
        obj.data.materials[slot] = mat

    # ---------------------------------------------------------------- uv

    def unwrap(self, object_id: str, *, method: str = "angle_based", margin: float = 0.001) -> None:
        import bpy

        obj = get_object(object_id)
        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        bpy.ops.object.mode_set(mode="EDIT")
        try:
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.unwrap(method=_UNWRAP_METHODS.get(method, method.upper()), margin=margin)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

    def mark_seams(self, object_id: str, edge_indices: Sequence[int]) -> None:
        """Unlike ``ModifierOps.bevel_edges`` (see ``modifiers._resolve_edges``),
        ``check_mark_seams_changes_the_subsequent_unwrap`` passes literal *positions* into a
        ``.edges()``-ordered list (``range(4)``), matching the Protocol's ``Sequence[int]``
        hint here. ``canonical_edges`` recomputes that exact ordering (kept in lock-step
        with ``MeshSnapshot.edges()`` — see ``_shared.py``) to translate position -> real
        edge."""
        import bmesh

        obj = get_object(object_id)
        mesh = obj.data
        _, triangles, _, orig_of = build_snapshot_topology(mesh)
        canonical = canonical_edges(triangles)

        bm = bmesh.new()
        bm.from_mesh(mesh)
        lookup = edge_lookup_by_original_vertices(bm.edges)
        for idx in edge_indices:
            a, b = canonical[idx]
            edge = lookup.get(frozenset((orig_of[a], orig_of[b])))
            if edge is not None:
                edge.seam = True
        write_bmesh(bm, obj)

    def bake(
        self, object_id: str, channels: Sequence[str], resolution: int, output_dir: str
    ) -> dict[str, str]:
        """Validate the cheap "has this been unwrapped" precondition before anything
        capability-gated, per ``conformance_surfacing.check_bake_requires_unwrap_first`` —
        so a caller who forgot to unwrap sees ``engine.not_unwrapped``, never a capability
        error that misdiagnoses their actual mistake as an environment limitation.

        The bake itself is a genuine attempt against Cycles, not a canned failure: this
        environment does have a windowed context and Cycles can be enabled at runtime
        (verified). Anything that goes wrong past the precondition check — no window after
        all, Cycles unavailable, no bakeable material — becomes
        :class:`EngineUnavailable("bake")` rather than a bare bpy exception, per
        ``UVBakeOps.bake``'s docstring.
        """
        obj = get_object(object_id)
        uv_layer = obj.data.uv_layers.active
        if uv_layer is None or len(uv_layer.data) == 0:
            raise EngineError(
                "engine.not_unwrapped", f"{object_id} has no UVs", "call unwrap() before bake()"
            )

        try:
            return self._bake_channels(obj, channels, resolution, output_dir)
        except EngineUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — must never leak a bare bpy exception
            raise EngineUnavailable("bake") from exc

    def _bake_channels(self, obj, channels: Sequence[str], resolution: int, output_dir: str) -> dict[str, str]:
        import os

        import bpy

        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        if not any(m is not None for m in obj.data.materials):
            mat = bpy.data.materials.new(f"{obj.name}_bake_material")
            mat.use_nodes = True
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        try:
            bpy.ops.preferences.addon_enable(module="cycles")
        except Exception:
            pass
        bpy.context.scene.render.engine = "CYCLES"

        os.makedirs(output_dir, exist_ok=True)
        results: dict[str, str] = {}
        for channel in channels:
            bake_type, pass_filter = _BAKE_TYPES.get(channel, ("DIFFUSE", {"COLOR"}))
            image = bpy.data.images.new(f"{obj.name}_{channel}_bake", width=resolution, height=resolution)

            for mat in obj.data.materials:
                if mat is None or not mat.use_nodes:
                    continue
                nt = mat.node_tree
                for node in nt.nodes:
                    node.select = False
                img_node = nt.nodes.new("ShaderNodeTexImage")
                img_node.image = image
                img_node.select = True
                nt.nodes.active = img_node

            kwargs = {"type": bake_type, "margin": 4}
            if pass_filter:
                kwargs["pass_filter"] = pass_filter
            bpy.ops.object.bake(**kwargs)

            out_path = os.path.join(output_dir, f"{obj.name}_{channel}.png")
            image.filepath_raw = out_path
            image.file_format = "PNG"
            image.save()
            results[channel] = out_path

        return results
