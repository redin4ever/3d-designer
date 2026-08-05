"""Per-engine export profiles — data only, no conversion logic.

The conversion *functions* and their round-trip fixtures live in ``src/export/``. Only the
numbers are frozen here, so ``export`` (which converts) and ``measure`` (which checks
polygon budgets) can both depend on this table without depending on each other.

The Blender Z-up-right-handed → glTF Y-up-right-handed → Unity Y-up-**left**-handed chain
is a documented, repeatedly-reported bug source. Its signature is mirrored geometry or
inverted rotations that appear only after a full export→import round trip — discovered in
a different tool than the one that caused it, which is exactly what makes it expensive.
ADR-010 puts every such conversion behind one audited function per profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "UpAxis",
    "Handedness",
    "AssetClass",
    "ExportProfile",
    "PROFILES",
    "DEFAULT_PROFILE",
    "profile_for",
]


class UpAxis(StrEnum):
    Y = "Y"
    Z = "Z"


class Handedness(StrEnum):
    RIGHT = "right"
    LEFT = "left"


class AssetClass(StrEnum):
    """Polygon budgets are stated per class. Tracked and warned against, never enforced
    (Gate A 12.2) — detail passes are what run the count up, so the warning fires where
    it is useful rather than blocking work the user wanted."""

    BACKGROUND_PROP = "background_prop"
    STANDARD_PROP = "standard_prop"
    HERO_PROP = "hero_prop"
    ENVIRONMENT_PIECE = "environment_piece"
    CHARACTER = "character"


@dataclass(frozen=True, slots=True)
class ExportProfile:
    name: str
    up_axis: UpAxis
    handedness: Handedness
    metres_per_unit: float
    """Multiply internal metres by ``1 / metres_per_unit`` to get target units."""

    unit_name: str
    flip_x: bool
    """True when going from a right-handed to a left-handed system. Combined with
    ``negate_rotation`` because flipping an axis alone leaves rotations inverted — a
    positive rotation is clockwise in a left-handed system and counter-clockwise in a
    right-handed one."""

    negate_rotation: bool
    max_triangles_per_mesh: int | None = None
    """Hard ceiling imposed by the target itself, not a style preference. ``None`` means
    the target imposes none."""

    budgets: dict[AssetClass, int] = field(default_factory=dict)
    notes: str = ""

    def to_target_units(self, metres: float) -> float:
        return metres / self.metres_per_unit

    def from_target_units(self, value: float) -> float:
        return value * self.metres_per_unit


#: Industry rule-of-thumb triangle budgets, shared where a target imposes nothing of its
#: own. These are advisory defaults the user can override per project.
_GENERAL_BUDGETS: dict[AssetClass, int] = {
    AssetClass.BACKGROUND_PROP: 800,
    AssetClass.STANDARD_PROP: 4_000,
    AssetClass.HERO_PROP: 20_000,
    AssetClass.ENVIRONMENT_PIECE: 10_000,
    AssetClass.CHARACTER: 40_000,
}


PROFILES: dict[str, ExportProfile] = {
    "roblox": ExportProfile(
        name="roblox",
        up_axis=UpAxis.Y,
        handedness=Handedness.RIGHT,
        metres_per_unit=0.28,
        unit_name="stud",
        flip_x=False,
        negate_rotation=False,
        max_triangles_per_mesh=10_000,
        budgets={
            AssetClass.BACKGROUND_PROP: 600,
            AssetClass.STANDARD_PROP: 2_500,
            AssetClass.HERO_PROP: 8_000,
            AssetClass.ENVIRONMENT_PIECE: 5_000,
            AssetClass.CHARACTER: 9_000,
        },
        notes=(
            "Primary target — the user's usual engine. The stud unit makes this the "
            "profile most likely to surface a scale bug, which argues for it being "
            "primary rather than against it. The per-MeshPart triangle ceiling is a "
            "platform limit, not a preference: exceeding it fails import outright, so "
            "budgets here sit deliberately below the general defaults."
        ),
    ),
    "unity": ExportProfile(
        name="unity",
        up_axis=UpAxis.Y,
        handedness=Handedness.LEFT,
        metres_per_unit=1.0,
        unit_name="m",
        flip_x=True,
        negate_rotation=True,
        budgets=dict(_GENERAL_BUDGETS),
        notes=(
            "The riskiest conversion of the four: Y-up but LEFT-handed, so it needs both "
            "an X flip and a rotation-sign correction. Getting one and not the other "
            "produces geometry that looks right and rotates wrong, or vice versa — the "
            "classic silent round-trip failure."
        ),
    ),
    "unreal": ExportProfile(
        name="unreal",
        up_axis=UpAxis.Z,
        handedness=Handedness.LEFT,
        metres_per_unit=0.01,
        unit_name="cm",
        flip_x=False,
        negate_rotation=True,
        budgets=dict(_GENERAL_BUDGETS),
        notes="Z-up like Blender, but left-handed and centimetre-scaled.",
    ),
    "godot": ExportProfile(
        name="godot",
        up_axis=UpAxis.Y,
        handedness=Handedness.RIGHT,
        metres_per_unit=1.0,
        unit_name="m",
        flip_x=False,
        negate_rotation=False,
        budgets=dict(_GENERAL_BUDGETS),
        notes="Closest to glTF's own convention — the least conversion risk of the four.",
    ),
}

DEFAULT_PROFILE = "roblox"


def profile_for(name: str) -> ExportProfile:
    key = name.strip().lower()
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise KeyError(f"unknown export profile {name!r}; known profiles: {known}")
    return PROFILES[key]
