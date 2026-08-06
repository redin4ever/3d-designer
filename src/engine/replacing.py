"""``MeshOps.replace_mesh`` — swap an object's geometry, keep everything that is not geometry.

A file of its own rather than another method on ``mesh.py`` because the decision here is not
"make a mesh" but "**preserve** across a mesh swap" (Rule 2 seam #1, a distinct decision):
which of an object's non-geometric attachments survive a new vertex set, which cannot, and
what to do with the ones that only sometimes can. ``mesh.py``'s creation methods all start
from nothing and have no such question to answer.

The three outcomes, and why each is what it is:

- **Transform** survives untouched. Only ``obj.data`` is replaced; ``obj.location``/
  ``rotation_quaternion``/``scale`` and therefore ``matrix_world`` are never written. This is
  the whole reason the method exists — delete-then-``create_mesh`` under the same id resets
  the object to the origin, so a topology cleanup would *move the model* as a side effect.
- **Material slots** survive, in order, pointing at the same material datablocks. Per-face
  material indices survive only when the replacement face list is the same length as the old
  one (see ``_carry_material_indices``), because otherwise there is no correspondence between
  old face *i* and new face *i* to carry.
- **UVs and seams are dropped, honestly.** Blender stores UVs per face *corner*, and seams
  are flags on specific edges; a new vertex and edge set has no correspondence to either. A
  UV layer kept across an arbitrary geometry swap is not a preserved unwrap, it is a wrong
  one that still reads as unwrapped to every later check — including ``bake``'s precondition.
  ``FakeEngine.replace_mesh`` drops them for exactly this reason and says so in its docstring;
  this engine matches it deliberately, so a caller that needs UVs afterwards re-unwraps on
  both backends rather than on one.

Note that the last point makes ``contracts.MeshOps.replace_mesh``'s "…and UV layers survive"
too strong for either implementation; recorded as a contract request rather than silently
implemented one way here and another way in the fake.
"""

from __future__ import annotations

from typing import Sequence

from contracts import EngineError, Vec3

from ._shared import get_object, write_bmesh

__all__ = ["MeshReplaceMixin"]


def _carry_material_indices(new_mesh, old_indices: list[int], slot_count: int) -> None:
    """Copy per-face material indices onto ``new_mesh`` when they still mean something.

    "Still mean something" is face-count parity. A caller that hands back the same number of
    faces (a vertex-welding or re-projection pass, say) has a face *i* that corresponds to the
    old face *i*; a caller that hands back a different number does not, and guessing an
    alignment there would put the wrong material on the wrong face — worse than the honest
    fallback of leaving every face on slot 0, which at least looks wrong immediately.

    Indices are clamped to the surviving slot range regardless. An index past the end of
    ``mesh.materials`` renders as the *last* slot in Blender rather than erroring, so an
    out-of-range value is a silent mis-assignment, not a loud one.
    """
    if slot_count == 0 or len(old_indices) != len(new_mesh.polygons):
        return
    limit = slot_count - 1
    for poly, index in zip(new_mesh.polygons, old_indices):
        poly.material_index = min(max(index, 0), limit)


class MeshReplaceMixin:
    """``MeshOps.replace_mesh``, mixed into :class:`~engine.session.BlenderEngine`."""

    def replace_mesh(
        self,
        object_id: str,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
    ) -> None:
        import bmesh
        import bpy

        obj = get_object(object_id)  # raises engine.unknown_object, naming what exists
        if not vertices:
            raise EngineError(
                "engine.empty_mesh",
                "a mesh needs at least one vertex",
                "pass the replacement geometry, or call delete() if the object should go",
            )

        old = obj.data
        old_name = old.name
        slots = list(old.materials)
        old_indices = [poly.material_index for poly in old.polygons]

        new_mesh = bpy.data.meshes.new(old_name)
        new_mesh.from_pydata([v.as_tuple() for v in vertices], [], [list(f) for f in faces])
        new_mesh.update()
        for material in slots:
            new_mesh.materials.append(material)
        _carry_material_indices(new_mesh, old_indices, len(slots))

        obj.data = new_mesh
        if old.users == 0:
            bpy.data.meshes.remove(old)
            new_mesh.name = old_name  # reclaim the name bpy uniquified around the old block

        # Invariant #1 (see ``_shared``): every stored mesh is fully triangulated. The caller
        # is free to hand over quads or ngons — ``create_mesh`` accepts them too — so the
        # write-back has to go through ``write_bmesh`` rather than stopping at ``from_pydata``.
        # ``bmesh.ops.triangulate`` carries each source face's ``material_index`` onto every
        # triangle it produces, so the assignment above survives the retriangulation.
        bm = bmesh.new()
        bm.from_mesh(new_mesh)
        write_bmesh(bm, obj)
