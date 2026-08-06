"""``snapshot_to_payload``/``transform_payload``: the boundary conversion into the wire
protocol's flat, typed-array-friendly buffers (ADR-011).
"""

from __future__ import annotations

from contracts import MeshSnapshot, Quat, Transform, Vec3

from viewer import snapshot_to_payload, transform_payload


def _quad_snapshot(**kwargs) -> MeshSnapshot:
    verts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(0, 1, 0)]
    tris = [(0, 1, 2), (0, 2, 3)]
    return MeshSnapshot(object_id="obj", vertices=verts, triangles=tris, **kwargs)


def test_positions_are_a_flat_list_of_length_3_times_vertex_count() -> None:
    """BufferGeometry attributes are flat typed arrays; a nested per-vertex object here
    is exactly the shape ADR-011 rejects for a thousands-of-objects scene."""
    snap = _quad_snapshot()
    payload = snapshot_to_payload(snap)

    assert payload.positions == [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0]
    assert len(payload.positions) == 3 * snap.vertex_count
    assert all(isinstance(c, float) for c in payload.positions)


def test_indices_are_a_flat_list_of_length_3_times_triangle_count() -> None:
    snap = _quad_snapshot()
    payload = snapshot_to_payload(snap)

    assert payload.indices == [0, 1, 2, 0, 2, 3]
    assert len(payload.indices) == 3 * snap.triangle_count
    assert all(isinstance(i, int) for i in payload.indices)


def test_multi_material_snapshot_populates_materials_and_groups_not_just_the_first_slot() -> None:
    """Keeping only the first material slot is a rendering bug that presents as a
    modelling bug (``MeshPayload.materials``'s own docstring)."""
    verts = [Vec3(float(i), 0, 0) for i in range(6)]
    tris = [(0, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, 5)]
    snap = MeshSnapshot(
        object_id="multi",
        vertices=verts,
        triangles=tris,
        material_slots=("wood", "metal"),
        triangle_materials=(0, 0, 1, 1),
    )

    payload = snapshot_to_payload(snap)

    assert payload.materials == ("wood", "metal")
    assert payload.groups == ((0, 6, 0), (6, 6, 1))


def test_single_material_snapshot_has_empty_groups() -> None:
    """Empty means "the whole mesh uses materials[0]" (``MeshPayload.groups``'s own
    docstring) — a group list here would be a lie about draw ranges that do not exist."""
    snap = _quad_snapshot(material_slots=("wood",))
    payload = snapshot_to_payload(snap)

    assert payload.materials == ("wood",)
    assert payload.groups == ()


def test_no_materials_at_all_round_trips_to_empty_tuples() -> None:
    snap = _quad_snapshot()
    payload = snapshot_to_payload(snap)

    assert payload.materials == ()
    assert payload.groups == ()


def test_object_id_and_triangle_count_carry_through() -> None:
    snap = _quad_snapshot()
    payload = snapshot_to_payload(snap)

    assert payload.object_id == "obj"
    assert payload.triangle_count == 2


def test_transform_payload_emits_quaternion_in_threejs_xyzw_order_not_wfirst() -> None:
    """``contracts.Quat`` is stored w-first internally (its own docstring). Converting
    once at the boundary is the whole point of this function; asserting the order
    explicitly is the only way this bug is visible in a test — on screen it looks like
    something merely spinning wrong."""
    t = Transform(translation=Vec3(1, 2, 3), rotation=Quat(w=0.5, x=0.1, y=0.2, z=0.3))
    snap = MeshSnapshot(object_id="o", vertices=[Vec3()], triangles=[], transform=t)

    payload = transform_payload(snap)

    assert payload.quaternion == (0.1, 0.2, 0.3, 0.5)
    assert payload.quaternion != (0.5, 0.1, 0.2, 0.3)  # the w-first order, to make the bug visible
    assert payload.position == (1.0, 2.0, 3.0)


def test_transform_payload_carries_scale_and_object_id() -> None:
    t = Transform(scale=Vec3(2, 2, 2))
    snap = MeshSnapshot(object_id="scaled", vertices=[Vec3()], triangles=[], transform=t)

    payload = transform_payload(snap)

    assert payload.object_id == "scaled"
    assert payload.scale == (2.0, 2.0, 2.0)
