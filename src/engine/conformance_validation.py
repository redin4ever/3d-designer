"""Conformance checks for the documented ``EngineError`` validation rules.

A distinct seam by decision, not by actor (Rule 2's seam #1: "validation"): every rule name
here is asserted verbatim against ``exc.value.rule`` because that string is what a calling
agent branches on (Gate A 4.2). Before this file, only ``engine.unapplied_scale``,
``engine.unknown_object`` and ``engine.not_unwrapped`` had any check at all — a real engine
that silently accepted an empty mesh or an invalid boolean solver was invisible to this
suite. Added in response to a conformance audit; ``engine.bad_bevel_width`` is the one
documented rule still without a check here — flagged, not added, to keep this pass scoped
to what was asked.
"""

from __future__ import annotations

import pytest

from contracts import EngineError, EngineProtocol, Vec3

__all__ = [
    "check_create_mesh_rejects_an_empty_vertex_list",
    "check_create_primitive_rejects_an_unknown_kind",
    "check_boolean_rejects_an_unknown_mode",
    "check_boolean_rejects_an_unknown_solver",
    "check_solidify_rejects_non_positive_thickness",
    "check_array_along_curve_rejects_non_positive_spacing",
    "check_array_along_curve_rejects_a_curve_with_fewer_than_two_points",
    "check_decimate_rejects_a_ratio_outside_the_unit_interval",
    "check_export_gltf_rejects_an_empty_object_list",
    "check_export_gltf_rejects_non_positive_scale",
    "check_set_pbr_rejects_an_unknown_material",
]


def check_create_mesh_rejects_an_empty_vertex_list(engine: EngineProtocol) -> None:
    """A mesh with zero vertices is not a mesh — accepting one silently produces an object
    every downstream snapshot/bounds call then crashes on, far from where the bad input was
    actually supplied."""
    with pytest.raises(EngineError) as exc:
        engine.create_mesh("empty", [], [])
    assert exc.value.rule == "engine.empty_mesh"


def check_create_primitive_rejects_an_unknown_kind(engine: EngineProtocol) -> None:
    """An unrecognised ``kind`` silently producing *something* (or nothing) leaves a caller
    unable to tell "typo in the kind string" from "the primitive is somewhere else"."""
    with pytest.raises(EngineError) as exc:
        engine.create_primitive("box", "dodecahedron", Vec3(1, 1, 1))
    assert exc.value.rule == "engine.unknown_primitive"


def check_boolean_rejects_an_unknown_mode(engine: EngineProtocol) -> None:
    """``mode`` is a closed set (union/difference/intersect); a coerced-to-default mode
    silently changes what a caller asked for into something else with no error."""
    a = engine.create_primitive("bmode_a", "cube", Vec3(1, 1, 1))
    b = engine.create_primitive("bmode_b", "cube", Vec3(1, 1, 1))
    with pytest.raises(EngineError) as exc:
        engine.boolean(a, b, mode="xor")
    assert exc.value.rule == "engine.bad_boolean_mode"


def check_boolean_rejects_an_unknown_solver(engine: EngineProtocol) -> None:
    """The Protocol docstring is explicit that no solver is unconditionally correct;
    silently coercing an invalid one to a default hides exactly the choice a caller made
    to avoid a known solver bug."""
    a = engine.create_primitive("bsolver_a", "cube", Vec3(1, 1, 1))
    b = engine.create_primitive("bsolver_b", "cube", Vec3(1, 1, 1))
    with pytest.raises(EngineError) as exc:
        engine.boolean(a, b, mode="union", solver="voxel")
    assert exc.value.rule == "engine.bad_boolean_solver"


def check_solidify_rejects_non_positive_thickness(engine: EngineProtocol) -> None:
    """A zero or negative thickness silently producing a zero-volume or inverted shell is
    invisible until the exported asset is inspected up close."""
    oid = engine.create_primitive("plate", "cube", Vec3(1, 1, 1))
    with pytest.raises(EngineError) as exc:
        engine.solidify(oid, thickness=0.0)
    assert exc.value.rule == "engine.bad_thickness"


def check_array_along_curve_rejects_non_positive_spacing(engine: EngineProtocol) -> None:
    """Zero spacing either hangs on an infinite loop or silently produces one instance;
    neither is the caller's request."""
    engine.create_primitive("post", "cube", Vec3(0.1, 0.1, 0.5))
    with pytest.raises(EngineError) as exc:
        engine.array_along_curve(
            "post", [Vec3(0, 0, 0), Vec3(1, 0, 0)], spacing=0.0, keep_upright=True
        )
    assert exc.value.rule == "engine.bad_spacing"


def check_array_along_curve_rejects_a_curve_with_fewer_than_two_points(
    engine: EngineProtocol,
) -> None:
    """A single-point "curve" has no direction to instance along; silently placing one
    instance at that point hides the caller's malformed input."""
    engine.create_primitive("post", "cube", Vec3(0.1, 0.1, 0.5))
    with pytest.raises(EngineError) as exc:
        engine.array_along_curve("post", [Vec3(0, 0, 0)], spacing=1.0, keep_upright=True)
    assert exc.value.rule == "engine.short_curve"


def check_decimate_rejects_a_ratio_outside_the_unit_interval(engine: EngineProtocol) -> None:
    """A ratio above 1 or at/below 0 is not a reduction fraction; clamping it silently
    changes the requested budget without telling the caller."""
    oid = engine.create_primitive("blob", "cube", Vec3(1, 1, 1))
    with pytest.raises(EngineError) as exc:
        engine.decimate(oid, ratio=1.5)
    assert exc.value.rule == "engine.bad_ratio"


def check_export_gltf_rejects_an_empty_object_list(
    engine: EngineProtocol, tmp_path
) -> None:
    """An export with nothing selected silently writing an empty (or missing) file is worse
    than raising — the caller reports success for an asset that was never selected."""
    with pytest.raises(EngineError) as exc:
        engine.export_gltf([], str(tmp_path / "out.glb"), y_up=True)
    assert exc.value.rule == "engine.nothing_to_export"


def check_export_gltf_rejects_non_positive_scale(engine: EngineProtocol, tmp_path) -> None:
    """A zero or negative scale silently collapsing or inverting the exported asset is
    invisible until the asset is loaded somewhere else."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    with pytest.raises(EngineError) as exc:
        engine.export_gltf([oid], str(tmp_path / "out.glb"), y_up=True, scale=0.0)
    assert exc.value.rule == "engine.bad_export_scale"


def check_set_pbr_rejects_an_unknown_material(engine: EngineProtocol) -> None:
    """Writing PBR values to a material id that does not exist and silently doing nothing
    is indistinguishable from success until the render comes back wrong."""
    with pytest.raises(EngineError) as exc:
        engine.set_pbr("does_not_exist", roughness=0.5)
    assert exc.value.rule == "engine.unknown_material"
