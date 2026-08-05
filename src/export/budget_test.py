"""Tests for triangle-budget checks against a target profile.

ADR-010 / Gate A 12.2: polygon budgets are tracked and warned against, never enforced by
this tool. But Roblox's per-mesh ceiling is different in kind from the advisory per-class
numbers — it is the platform itself that refuses the import, not a style preference — so a
defect from crossing it has to name the exact overage, not just raise a flag, so an agent
knows how much to decimate.
"""

from __future__ import annotations

import pytest

from contracts import AssetClass, DefectClass, Vec3, profile_for
from export import check_budget

ROBLOX = profile_for("roblox")
UNITY = profile_for("unity")


def _mesh_with_triangles(engine, object_id: str, count: int) -> str:
    """A minimal 3-vertex mesh repeated into ``count`` triangular faces. Every face
    triangulates to exactly one triangle (see ``FakeObject.triangulated``), so the
    resulting ``snapshot().triangle_count`` is exactly ``count`` — the geometry does not
    need to be a sensible shape for a budget check, which only counts triangles."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)]
    faces = [(0, 1, 2)] * count
    return engine.create_mesh(object_id, verts, faces)


def test_mesh_over_the_hard_ceiling_yields_one_defect_sized_to_the_overage(engine) -> None:
    """Roblox's 10,000-triangle-per-MeshPart ceiling is a platform limit: crossing it fails
    import outright. The agent needs the exact overage, not just a yes/no flag, to know how
    much to decimate before trying again."""
    _mesh_with_triangles(engine, "heavy", 12_000)

    defects = check_budget(engine, ["heavy"], ROBLOX)

    assert len(defects) == 1
    d = defects[0]
    assert d.defect_class is DefectClass.BUDGET_EXCEEDED
    assert d.object_id == "heavy"
    assert d.magnitude == pytest.approx(2_000)


def test_mesh_under_the_hard_ceiling_yields_nothing(engine) -> None:
    """A false positive here would put a warning banner on every ordinary export; an agent
    that learns to ignore budget warnings because they fire constantly stops trusting the
    one warning that actually matters."""
    _mesh_with_triangles(engine, "light", 50)

    assert check_budget(engine, ["light"], ROBLOX) == ()


def test_asset_class_selects_the_per_class_budget_instead_of_the_hard_ceiling(engine) -> None:
    """Roblox's BACKGROUND_PROP budget (600) is far below its 10,000-triangle hard ceiling.
    The same 700-triangle mesh must flag when checked against the class budget and clear
    when checked without one — an implementation that ignores ``asset_class`` and always
    falls back to ``max_triangles_per_mesh`` would silently wave through a background prop
    at more than ten times its class's allowance."""
    _mesh_with_triangles(engine, "prop", 700)

    with_class = check_budget(engine, ["prop"], ROBLOX, asset_class=AssetClass.BACKGROUND_PROP)
    without_class = check_budget(engine, ["prop"], ROBLOX)

    assert len(with_class) == 1
    assert with_class[0].magnitude == pytest.approx(100)
    assert without_class == ()


def test_no_ceiling_declared_means_nothing_is_ever_flagged(engine) -> None:
    """Unity, Unreal and Godot declare no ``max_triangles_per_mesh`` — only Roblox's
    per-MeshPart ceiling is a platform fact this tool knows about. Checking without an
    ``asset_class`` against one of the other three must never invent a limit that was never
    declared, no matter how heavy the mesh is."""
    _mesh_with_triangles(engine, "huge", 500_000)

    assert check_budget(engine, ["huge"], UNITY) == ()


def test_multiple_objects_are_each_checked_independently(engine) -> None:
    """A budget check that only looks at the first object in the list, or that pools
    triangle counts across objects, would miss a second heavy mesh or wrongly flag two
    light ones sitting side by side — this is the case that catches either mistake."""
    _mesh_with_triangles(engine, "heavy_a", 11_000)
    _mesh_with_triangles(engine, "light_a", 100)

    defects = check_budget(engine, ["heavy_a", "light_a"], ROBLOX)

    assert {d.object_id for d in defects} == {"heavy_a"}
