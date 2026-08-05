"""Tests for the pure axis/handedness/unit conversion at the export boundary.

These are pure functions over plain data (``Vec3``, ``Quat``, ``float``) and a frozen
``ExportProfile`` — no engine, no bpy, no fixture. The round-trip and per-profile fixtures
here are exactly what ADR-010 calls "one audited conversion function per profile, tested
with a round-trip fixture that would catch a mirror or a rotation-sign inversion." A failure
here means a model exported for the named engine comes out mirrored or rotated wrong,
discovered only after a full export -> import round trip, in a different tool than the one
that produced it.
"""

from __future__ import annotations

import math

import pytest

from contracts import EPSILON, Quat, Vec3, profile_for
from export import convert_point, convert_quaternion, convert_scalar, round_trip

ROBLOX = profile_for("roblox")
UNITY = profile_for("unity")
UNREAL = profile_for("unreal")
GODOT = profile_for("godot")
ALL_PROFILES = (ROBLOX, UNITY, UNREAL, GODOT)

#: Asymmetric on purpose: x != y != z and at least one component negative. A symmetric
#: point (e.g. all-equal or all-zero components) would pass a round trip even if two axes
#: were silently swapped, proving nothing about which axis actually moved.
ASYMMETRIC_POINTS = (
    Vec3(1.5, -2.5, 3.5),
    Vec3(-4.25, 6.0, -0.75),
)


# --------------------------------------------------------------------------- round trip


@pytest.mark.parametrize("p", ASYMMETRIC_POINTS)
@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda pr: pr.name)
def test_round_trip_recovers_the_original_point(profile, p) -> None:
    """A round trip that does not return the original point means ``convert_point`` and its
    inverse disagree about this profile's axis/handedness/unit convention — exactly the
    export -> import mismatch a user would otherwise discover only after re-opening the
    file in Roblox, Unity, Unreal or Godot, in a session that has nothing to do with the
    tool that produced the file."""
    result = round_trip(p, profile)

    assert result.x == pytest.approx(p.x, abs=EPSILON)
    assert result.y == pytest.approx(p.y, abs=EPSILON)
    assert result.z == pytest.approx(p.z, abs=EPSILON)


# ------------------------------------------------------------------------------- roblox


def test_roblox_converts_metres_to_studs() -> None:
    """1 stud = 0.28 m is the exact constant Gate A 12.1 fixes for the user's primary
    target. A wrong constant here makes every exported Roblox model the wrong physical size
    in-engine, with no visual tell until it is placed next to a genuine Roblox part."""
    assert convert_scalar(2.8, ROBLOX) == pytest.approx(10.0)


def test_roblox_moves_blender_height_onto_the_target_up_axis() -> None:
    """Roblox is Y-up; a point 1 m up along Blender's Z must land on the target's Y, not
    stay on Z. A conversion that returns its input unchanged (or applies only the unit
    scale and forgets the axis remap) passes no other test in this file but would pass a
    "does it run" smoke test — and would produce a model that imports lying on its side."""
    p = Vec3(0.0, 0.0, 1.0)

    result = convert_point(p, ROBLOX)

    assert result.y != pytest.approx(0.0)
    assert result.y == pytest.approx(1.0 / ROBLOX.metres_per_unit)
    assert result.z == pytest.approx(0.0, abs=EPSILON)


# -------------------------------------------------------------------------------- unity


def test_unity_negates_x() -> None:
    """Unity is the one LEFT-handed target of the four (ADR-010's riskiest conversion).
    Isolated on an axis the up-axis remap does not touch (X), so this proves the mirror
    alone, independent of the Y-up remap tested next — a conversion that mirrors nothing
    produces geometry that is a perfect match for a left hand held up to a mirror: it looks
    plausible and is wrong."""
    p = Vec3(1.0, 0.0, 0.0)

    result = convert_point(p, UNITY)

    assert result.x == pytest.approx(-1.0)


def test_unity_moves_z_onto_y_like_any_y_up_target() -> None:
    """Unity's up-axis handling must behave like Roblox's and Godot's — the LEFT-handed
    correction is a separate, additional step, not a replacement for the ordinary Y-up
    remap. An implementation that special-cases Unity and forgets the shared remap would
    still pass the X-negation test above while failing this one."""
    p = Vec3(0.0, 0.0, 1.0)

    result = convert_point(p, UNITY)

    assert result.y == pytest.approx(1.0)
    assert result.z == pytest.approx(0.0, abs=EPSILON)


def test_unity_flips_a_rotations_sign() -> None:
    """The bug this module exists to prevent: mirroring position alone leaves every
    rotation inverted, because a positive rotation is clockwise in a left-handed system and
    counter-clockwise in a right-handed one (ADR-010). Rotate the same probe vector by a
    known rotation converted through Unity (mirror + rotation-sign correction) and through
    Godot (same up-axis remap, no correction at all) and the two must send the probe in
    opposite directions. A converter that mirrors positions but forgets
    ``negate_rotation`` would make these identical and still pass both tests above — a
    model that looks right in a screenshot and rotates the wrong way the moment it moves."""
    # +90 degrees about Blender's world-up Z axis — after the shared Y-up remap this
    # becomes a rotation purely about the target's Y axis, which unity's X-only mirror
    # cannot touch. That isolates exactly what negate_rotation contributes.
    q = Quat.from_axis_angle(Vec3(0, 0, 1), math.pi / 2)
    probe = Vec3(1.0, 0.0, 0.0)

    unity_q = convert_quaternion(q, UNITY)
    godot_q = convert_quaternion(q, GODOT)

    assert unity_q != godot_q
    rotated_by_unity = unity_q.rotate(probe)
    rotated_by_godot = godot_q.rotate(probe)
    assert rotated_by_godot.z != pytest.approx(0.0)
    assert rotated_by_unity.z == pytest.approx(-rotated_by_godot.z, abs=1e-6)


# ------------------------------------------------------------------------------- unreal


def test_unreal_converts_metres_to_centimetres() -> None:
    """0.01 m per Unreal unit (Gate A 12.1's table, ×100 from the internal metre
    convention). A wrong constant here makes every Unreal export 100x or 1/100x the
    intended size — obvious once placed in-engine, but invisible in the file itself."""
    assert convert_scalar(1.0, UNREAL) == pytest.approx(100.0)


def test_unreal_needs_no_axis_swap() -> None:
    """Unreal is Z-up like Blender's internal convention — the one profile of the four that
    must NOT remap height onto a different axis. Checking all three axes (not just Z) is
    what catches an implementation that always applies the Y-up remap regardless of profile
    and would move Unreal's height axis too."""
    p = Vec3(1.5, -2.5, 3.5)
    scale = 1.0 / UNREAL.metres_per_unit

    result = convert_point(p, UNREAL)

    assert result.x == pytest.approx(p.x * scale)
    assert result.y == pytest.approx(p.y * scale)
    assert result.z == pytest.approx(p.z * scale)


# -------------------------------------------------------------------------------- godot


def test_godot_needs_no_mirror() -> None:
    """Godot is the profile closest to glTF's own convention — right-handed, so X must come
    through unmirrored, unlike Unity's. A converter that mirrors every Y-up target
    regardless of handedness would pass Unity's test and fail this one."""
    p = Vec3(1.5, -2.5, 3.5)

    result = convert_point(p, GODOT)

    assert result.x == pytest.approx(1.5)


# -------------------------------------------------------------------------- cross-profile


def test_unity_and_godot_disagree_on_the_same_point() -> None:
    """Unity and Godot share the same up-axis and unit scale and differ only in
    ``flip_x`` — an implementation that ignores that field entirely would produce identical
    output for both, silently passing every profile-specific test above by accident while
    still shipping Unity models mirrored the wrong way."""
    p = Vec3(1.5, -2.5, 3.5)

    assert convert_point(p, UNITY) != convert_point(p, GODOT)
