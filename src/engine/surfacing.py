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


def _rgba(base_color: Sequence[float]) -> tuple[float, float, float, float]:
    """Normalise a caller's base colour to the RGBA every bpy colour property expects.

    ``MaterialOps`` types ``base_color`` as RGB, but RGBA is what a caller round-tripping a
    colour out of anything Blender-shaped actually holds, and ``FakeEngine`` — which stores
    the tuple verbatim — accepts either. This engine used to append an alpha unconditionally,
    so the RGBA form became a 5-float sequence and bpy raised a raw ``ValueError`` naming
    neither the argument nor the caller. See
    ``conformance_materials.check_create_material_accepts_an_rgba_base_color``.
    """
    channels = tuple(float(c) for c in base_color)
    if len(channels) == 4:
        return channels
    if len(channels) == 3:
        return (*channels, 1.0)
    raise EngineError(
        "engine.bad_color",
        f"base_color has {len(channels)} components, expected 3 (RGB) or 4 (RGBA)",
        "pass (r, g, b) or (r, g, b, a) with each channel in 0..1",
    )


def _find_principled(node_tree):
    """The material's Principled BSDF, or ``None`` if it has no node tree or no such node.

    Never enable ``Material.use_nodes`` to get one. In Blender 5.2 every material returned by
    ``bpy.data.materials.new()`` already carries a shader node tree with a Principled BSDF and
    an Output — ``use_nodes`` is vestigial, and bpy marks it *deprecated, to be removed in
    Blender 6.0*, warning on **both** read and write.

    That deprecation is not cosmetic here. This repo runs pytest with
    ``filterwarnings = ["error::DeprecationWarning"]``, so touching ``use_nodes`` raises
    inside a C-level RNA setter, which cannot propagate it: bpy leaves the Python error
    indicator set and the *next* RNA type registration fails with
    ``ERROR failed to register 'ShaderNodeTree'``. Reading ``node_tree.nodes`` after that
    raises ``MemoryError: couldn't create BPy_rna object`` — a wrong, alarming error, several
    calls away from the line that actually caused it.
    """
    if node_tree is None:
        return None
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

        rgba = _rgba(base_color)
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = rgba
        bsdf = _find_principled(mat.node_tree)
        if bsdf is not None:
            socket = _find_input(bsdf, "Base Color", "Color")
            if socket is not None:
                socket.default_value = rgba
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
        bsdf = _find_principled(mat.node_tree)  # never via use_nodes — see _find_principled

        if base_color is not None:
            rgba = _rgba(base_color)
            mat.diffuse_color = rgba
            if bsdf is not None:
                socket = _find_input(bsdf, "Base Color", "Color")
                if socket is not None:
                    socket.default_value = rgba
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

    def create_texture_material(self, material: object) -> str:
        from engine.texture_materials import apply_to_blender

        name = getattr(material, "name", "")
        try:
            mat = get_material(name)
        except EngineError:
            self.create_material(name, (0.8, 0.8, 0.8))
            mat = get_material(name)
        apply_to_blender(name, material, mat)
        return name

    def assign_texture_material(
        self, object_id: str, material_id: str, slot: int = 0, material: object | None = None
    ) -> None:
        if material is not None:
            self.create_texture_material(material)
        self.assign_material(object_id, material_id, slot)

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
            if not 0 <= idx < len(canonical):
                continue  # a stale index costs one seam, not the whole unwrap
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
                if mat is None or mat.node_tree is None:  # not `use_nodes` — deprecated,
                    continue                              # and reading it poisons bpy's
                nt = mat.node_tree                        # error state (see _find_principled)
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
