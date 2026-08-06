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
    "check_create_material_accepts_an_rgba_base_color",
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


def check_create_material_accepts_an_rgba_base_color(engine: EngineProtocol) -> None:
    """A four-component base colour must work as well as a three-component one.

    ``MaterialOps`` types ``base_color`` as RGB, but RGBA is what a caller reading a colour
    back out of anything Blender-shaped has in hand — every bpy colour property, and
    ``FakeEngine``'s own stored value if it was given one — so a round-trip hands four
    components straight back in. ``FakeEngine`` stores whatever it is passed and so accepts
    both; the real engine wrote ``(*base_color, 1.0)`` into a 4-float bpy property and died
    with ``ValueError: sequences of dimension 0 should contain 4 items, not 5`` on the RGBA
    form. That is exactly the class of divergence this suite exists to catch: the fake said
    the call was fine, so every module tested against it believed a call that only the real
    backend rejects.

    Asserted through ``material_slots`` rather than by reading the colour back, because
    ``MaterialOps`` has no Protocol-level colour readback by design (see this module's
    docstring) — the observable is that the material exists and is usable, not its value.
    """
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    mat_id = engine.create_material("rgba_grey", (0.5, 0.5, 0.5, 1.0))
    engine.assign_material(oid, mat_id, slot=0)
    assert mat_id in engine.snapshot(oid).material_slots

    engine.set_pbr(mat_id, base_color=(0.2, 0.4, 0.6, 1.0), roughness=0.7)
    assert mat_id in engine.snapshot(oid).material_slots


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
