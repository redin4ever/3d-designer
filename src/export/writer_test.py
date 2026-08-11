"""Tests for ``export_scene`` and ``banner_for`` — the file-writing half of ``export``.

Gate A 6.3, verbatim user decision: export is allowed with a warning banner, never blocked.
These are the tests that would catch a regression back toward blocking, and the one that
would catch a conversion field silently dropped between the profile table and
``EngineProtocol.export_gltf`` — a bug invisible in the output file itself, only visible by
inspecting the call the engine actually received.
"""

from __future__ import annotations

import pytest

from contracts import DefectClass, Vec3, profile_for
from export import banner_for, export_scene


def _non_manifold_mesh(engine, object_id: str) -> str:
    """Three independent edges, each shared by three triangles — edges (0,1), (5,6) and
    (10,11) — and nothing else non-manifold: every other edge in this mesh bounds exactly
    one triangle. Three distinct NON_MANIFOLD_EDGE defects, not one defect counted three
    ways."""
    verts = [Vec3(float(i), 0.0, 0.0) for i in range(15)]
    faces = []
    for base in (0, 5, 10):
        for tip in (base + 2, base + 3, base + 4):
            faces.append((base, base + 1, tip))
    return engine.create_mesh(object_id, verts, faces)


# --------------------------------------------------------------------- conversion fields


def test_export_passes_every_conversion_field_to_the_engine_not_just_y_up(engine) -> None:
    """An earlier draft of ``ExportOps.export_gltf`` exposed only ``y_up``, which left
    ``mirror_x`` and ``negate_rotation`` — the two fields a left-handed target needs
    together — with no way to reach the exporter (``contracts/engine.py``). Unity is the
    profile where both are True, so this is the one call that catches either being silently
    dropped between the profile table and the engine boundary."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    report = export_scene(engine, ["box"], "out/box.glb", profile_name="unity")

    calls = [c for c in engine.calls if c[0] == "export_gltf"]
    assert len(calls) == 1
    _, (object_ids, path, y_up, mirror_x, negate_rotation, scale) = calls[0]
    assert tuple(object_ids) == ("box",)
    assert path == "out/box.glb"
    assert y_up is True
    assert mirror_x is True
    assert negate_rotation is True
    assert scale == pytest.approx(1.0)
    assert report.profile == "unity"


def test_export_for_roblox_passes_the_stud_scale_and_no_mirroring(engine) -> None:
    """Roblox is right-handed and Y-up like Unity, but must NOT mirror or negate rotation —
    the mirror image of the Unity test above, catching those two flags leaking into a
    profile that never asked for them, and catching the stud scale factor being dropped in
    favour of a bare 1.0."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    roblox = profile_for("roblox")

    export_scene(engine, ["box"], "out/box.glb", profile_name="roblox")

    _, (_, _, y_up, mirror_x, negate_rotation, scale) = next(
        c for c in engine.calls if c[0] == "export_gltf"
    )
    assert y_up is True
    assert mirror_x is False
    assert negate_rotation is False
    assert scale == pytest.approx(1.0 / roblox.metres_per_unit)


def test_non_gltf_editor_export_uses_the_generic_model_boundary(engine) -> None:
    """OBJ/FBX/STL/PLY/USD must not be silently routed through the glTF writer."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    report = export_scene(
        engine,
        ["box"],
        "out/box.obj",
        profile_name="generic",
        format_name="obj",
    )

    calls = [call for call in engine.calls if call[0] == "export_model"]
    assert len(calls) == 1
    assert calls[0][1][1].endswith("box.obj")
    assert report.profile == "generic"


# ------------------------------------------------------------------------- happy path


def test_clean_export_is_ok_and_reports_no_defects(engine) -> None:
    """The baseline every other test in this file is a variation of: geometry with nothing
    wrong should produce a report with nothing to warn about."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    report = export_scene(engine, ["box"], "out/box.glb", profile_name="godot")

    assert report.ok is True
    assert report.path == "out/box.glb"
    assert report.defects == ()
    assert "clean" in banner_for(report)


# --------------------------------------------------------------------- warning banner


def test_defects_never_block_the_export(engine) -> None:
    """This is the property Gate A 6.3 exists to guarantee: a scene with real,
    BLOCKER-severity defects (non-manifold edges fail on import into an engine or a
    slicer — ``contracts.measurement.DEFAULT_SEVERITY``) still produces a written file. An
    implementation that returns ``ok=False``, or raises, here contradicts an explicit user
    decision instead of merely getting geometry wrong."""
    _non_manifold_mesh(engine, "bad")

    report = export_scene(engine, ["bad"], "out/bad.glb", profile_name="roblox")

    assert report.ok is True
    assert report.path == "out/bad.glb"


def test_the_banner_names_every_one_of_the_three_defects(engine) -> None:
    """An export that silently succeeds over broken geometry is the exact failure the
    banner exists to prevent. A report that finds only one or two of the three edges would
    leave an agent thinking the mesh is closer to clean than it actually is, and it would
    fail on import anyway."""
    _non_manifold_mesh(engine, "bad")

    report = export_scene(engine, ["bad"], "out/bad.glb", profile_name="roblox")

    non_manifold = [d for d in report.defects if d.defect_class is DefectClass.NON_MANIFOLD_EDGE]
    assert len(non_manifold) == 3
    banner = banner_for(report)
    assert banner.count("non_manifold_edge") == 3


# --------------------------------------------------------------------------- forced


def test_forced_is_false_by_default_even_with_a_blocking_defect(engine) -> None:
    """``forced`` documents a knowing override (``contracts.ExportReport.forced``); it must
    not read True just because a BLOCKER-severity defect happened to be present — only when
    the caller actually passed ``force=True``."""
    _non_manifold_mesh(engine, "bad")

    report = export_scene(engine, ["bad"], "out/bad.glb", profile_name="roblox")

    assert report.forced is False


def test_force_true_is_recorded_when_a_blocking_defect_was_present(engine) -> None:
    """"Recorded, never silent" — ``contracts.ExportReport.forced``'s own docstring. An
    agent or a human reviewing this report later must be able to tell an override happened,
    not just that the export succeeded."""
    _non_manifold_mesh(engine, "bad")

    report = export_scene(engine, ["bad"], "out/bad.glb", profile_name="roblox", force=True)

    assert report.forced is True
    assert "forced" in banner_for(report).lower()


# --------------------------------------------------------------------------- budget


def test_export_report_carries_the_budget_overage(engine) -> None:
    """``ExportReport.banner`` renders ``over_budget_by``/``budget`` as a dedicated line
    distinct from the general defects list (see ``contracts/contracts_test.py::
    test_export_report_banner_states_what_is_wrong``) — ``export_scene`` has to populate
    those fields with the real numbers, not leave them at their zero/None defaults, or a
    scene twice over budget banners as clean."""
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)]
    faces = [(0, 1, 2)] * 12_000
    engine.create_mesh("heavy", verts, faces)

    report = export_scene(engine, ["heavy"], "out/heavy.glb", profile_name="roblox")

    assert report.ok is True
    assert report.budget == 10_000
    assert report.over_budget_by == 2_000
    assert report.triangle_count == 12_000
    assert "2000" in banner_for(report).replace(",", "")


# --------------------------------------------------------------------- unknown profile


def test_unknown_profile_names_the_four_that_exist(engine) -> None:
    """An agent that mistypes a profile name needs the list of real ones in the error
    message, not a bare ``KeyError`` it cannot act on (Gate A 4.2)."""
    engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    with pytest.raises(KeyError) as exc:
        export_scene(engine, ["box"], "out/box.glb", profile_name="cryengine")

    message = str(exc.value)
    for name in ("roblox", "unity", "unreal", "godot"):
        assert name in message
