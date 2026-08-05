"""Stub — pure axis/handedness/unit conversion at the export boundary. See
``src/export/README.md`` for the full contract.

The Blender Z-up-right-handed -> glTF Y-up-right-handed -> Unity Y-up-left-handed chain is
the documented, repeatedly-reported bug source ADR-010 exists to close: mirrored geometry or
inverted rotations that appear only after a full export -> import round trip, discovered in
a different tool than the one that caused them. Every function below is a pure function over
plain data (``Vec3``, ``Quat``, ``float``) and a ``contracts.ExportProfile`` — no engine, no
bpy — which is exactly why the round-trip fixture that catches the bug can live here rather
than in ``src/engine/``.

Nothing below computes anything yet — every function raises until an implementer replaces
the body.
"""

from __future__ import annotations

from contracts import ExportProfile, Quat, Vec3

__all__ = ["convert_point", "convert_quaternion", "convert_scalar", "round_trip"]


def convert_point(p: Vec3, profile: ExportProfile) -> Vec3:
    """Blender-native (Z-up, right-handed, metres) -> the target profile's axis, handedness
    and unit convention.

    Up-axis: when ``profile.up_axis`` is ``UpAxis.Y``, Blender's Z (height) becomes the
    target's Y and Blender's Y becomes the target's -Z — the same remap Blender's own glTF
    exporter uses to go from Z-up to Y-up without flipping handedness. ``UpAxis.Z`` targets
    (Unreal) keep Blender's axes exactly as-is; that profile's own handedness correction is
    carried entirely by ``flip_x``/``negate_rotation``, not by an axis swap.

    Handedness: ``profile.flip_x`` negates the resulting X, applied *after* the up-axis
    remap above.

    Units: the result is scaled by ``profile.to_target_units`` — equivalent to
    :func:`convert_scalar` applied to each component.
    """
    raise NotImplementedError("export.convert_point: not implemented")


def convert_quaternion(q: Quat, profile: ExportProfile) -> Quat:
    """Rotation counterpart of :func:`convert_point`.

    The vector part ``(x, y, z)`` goes through the identical up-axis remap and ``flip_x``
    mirror as a point; ``w`` is never touched. ``profile.negate_rotation`` then inverts the
    sense of the rotation — negates the (already remapped, already mirrored) vector part a
    second time — which is the correction a left-handed target needs *in addition to* the
    position mirror, per ADR-010: a positive rotation is clockwise in a left-handed system
    and counter-clockwise in a right-handed one, so mirroring position alone leaves every
    rotation inverted.
    """
    raise NotImplementedError("export.convert_quaternion: not implemented")


def convert_scalar(metres: float, profile: ExportProfile) -> float:
    """A length (bevel width, wall thickness, …) in Blender's internal metres, converted to
    the target profile's unit.

    Equivalent to ``profile.to_target_units(metres)``; exposed as its own function here so a
    caller converting a whole scene reaches one place (``export``) for every conversion it
    needs, rather than reaching past this module into ``contracts`` for units alone.
    """
    raise NotImplementedError("export.convert_scalar: not implemented")


def round_trip(p: Vec3, profile: ExportProfile) -> Vec3:
    """Convert ``p`` to ``profile`` and back through the true inverse of
    :func:`convert_point`. Must equal ``p`` within ``contracts.EPSILON`` for every profile —
    this is ADR-010's audited round-trip fixture: a mirror or a rotation-sign inversion
    introduced anywhere in :func:`convert_point` fails this for at least one axis on an
    asymmetric point (one where ``x != y != z`` and at least one component is negative — a
    symmetric point would pass even with two axes silently swapped).
    """
    raise NotImplementedError("export.round_trip: not implemented")
