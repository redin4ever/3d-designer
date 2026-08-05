"""Conformance checks for ``MaterialOps`` — never covered before this file.

``create_material``/``assign_material`` are checked universally through
``MeshSnapshot.material_slots`` (a real Protocol-level observable). ``set_pbr`` has no
Protocol-level readback at all by design — see ``contracts.MaterialOps`` — so verifying it
changed anything means either ``FakeEngine``'s test-only ``.material()`` accessor, or
introspecting a real material's Principled BSDF node sockets, whose names ADR-001 documents
as breaking between Blender versions with no deprecation policy. The fake accessor is the
only side of that choice which is not fragile, so this file's ``set_pbr`` check is fake-only.
"""

from __future__ import annotations

import pytest

from contracts import EngineProtocol, Vec3

__all__ = [
    "check_create_material_and_assign_material_reach_the_snapshot",
    "check_set_pbr_updates_roughness_observably",
]


# ------------------------------------------------------------------------------ universal

def check_create_material_and_assign_material_reach_the_snapshot(
    engine: EngineProtocol,
) -> None:
    """create_material's returned id must be immediately usable by assign_material, and the
    assignment must actually reach the object — a no-op assign_material (or a
    create_material whose id nothing else recognizes) passes silently until an export ships
    with no material on it at all."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    mat_id = engine.create_material("red", (0.8, 0.05, 0.05))

    engine.assign_material(oid, mat_id, slot=0)

    slots = engine.snapshot(oid).material_slots
    assert mat_id in slots, f"assigned material {mat_id!r} not present in slots {slots!r}"


# ------------------------------------------------------------------------------ fake-only

def check_set_pbr_updates_roughness_observably(engine: EngineProtocol) -> None:
    """Fake-only — see module docstring. A no-op set_pbr means every surface in the product
    renders at Blender's default roughness regardless of what was requested, one of the
    loudest "this is CG" signals there is."""
    mat_id = engine.create_material("plastic", (0.5, 0.5, 0.5))

    engine.set_pbr(mat_id, roughness=0.9, metallic=0.0)

    mat = engine.material(mat_id)
    assert mat["roughness"] == pytest.approx(0.9)
    assert mat["metallic"] == pytest.approx(0.0)
