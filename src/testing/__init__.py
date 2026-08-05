"""Shared test infrastructure. Main-agent owned (Rule 5) — every module's tests use it.

Importing this package does not import bpy and never will. That is the point: it is what
lets `pytest` run the whole decision layer with no Blender installed.
"""

from .fake_engine import FakeEngine, FakeObject
from .mesh_helpers import (
    arc_length_to,
    boundary_loops,
    connected_components,
    rotation_from_up_to,
    sample_polyline,
    tangent_at,
    unit_cube,
)

__all__ = [
    "FakeEngine",
    "FakeObject",
    "unit_cube",
    "sample_polyline",
    "arc_length_to",
    "tangent_at",
    "rotation_from_up_to",
    "boundary_loops",
    "connected_components",
]
